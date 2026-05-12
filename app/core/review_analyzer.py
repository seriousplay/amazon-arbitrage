"""
差评分析引擎 — 关键词聚类 / 缺陷标签 / 改进建议
基于差评文本做结构化分析，不依赖外部 LLM API
"""

import math
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from app.models.review import (
    ComplaintCluster,
    ReviewAnalysis,
    ReviewAnalysisBatch,
    ReviewItem,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ─── 缺陷关键词库（按品类可扩展）──────────────────────

DEFECT_KEYWORDS = {
    "quality": {
        "keywords": [
            "cheap",
            "flimsy",
            "poor quality",
            "falls apart",
            "broken",
            "defective",
            "waste of money",
            "not durable",
            "cheaply made",
            "low quality",
            "broke",
            "cracked",
            "tear",
            "rip",
            "leak",
            "stopped working",
            "doesn't work",
            "malfunction",
            "defect",
            "劣质",
            "质量差",
            "易坏",
            "破损",
        ],
        "label": "质量缺陷",
        "severity": "高",
        "improvement": "升级材料品质，增加质检环节，重点关注易损部位加固",
    },
    "size_fit": {
        "keywords": [
            "too small",
            "too big",
            "runs small",
            "runs large",
            "doesn't fit",
            "wrong size",
            "size chart",
            "inaccurate sizing",
            "tight",
            "loose",
            "尺寸不对",
            "偏小",
            "偏大",
        ],
        "label": "尺寸/版型问题",
        "severity": "中",
        "improvement": "优化尺码表，增加尺寸实测图，考虑提供多尺寸选项",
    },
    "durability": {
        "keywords": [
            "lasted",
            "only lasted",
            "a few weeks",
            "a few months",
            "wore out",
            "faded",
            "peeling",
            "cracking",
            "rust",
            "不结实",
            "不耐用",
            "褪色",
            "掉色",
        ],
        "label": "耐久性不足",
        "severity": "高",
        "improvement": "更换更耐用的材料，加强接缝/边缘处理",
    },
    "functionality": {
        "keywords": [
            "doesn't work",
            "not as described",
            "doesn't do",
            "useless",
            "not effective",
            "does nothing",
            "功能不符",
            "没用",
            "效果差",
        ],
        "label": "功能不符",
        "severity": "高",
        "improvement": "优化产品功能设计，确保产品描述与实际功能一致",
    },
    "design": {
        "keywords": [
            "poor design",
            "bad design",
            "awkward",
            "uncomfortable",
            "unstable",
            "tips over",
            "falls over",
            "hard to use",
            "设计缺陷",
            "不好用",
            "不穩",
        ],
        "label": "设计缺陷",
        "severity": "中",
        "improvement": "根据用户反馈改进人体工学设计，优化使用体验",
    },
    "assembly": {
        "keywords": [
            "hard to assemble",
            "difficult to install",
            "instructions",
            "confusing",
            "missing parts",
            "hard to put together",
            "安装困难",
            "说明书不清楚",
            "缺少零件",
        ],
        "label": "安装/组装困难",
        "severity": "中",
        "improvement": "优化安装说明（多配图/视频二维码），附送必要工具",
    },
    "material": {
        "keywords": [
            "cheap material",
            "bad material",
            "plastic",
            "thin",
            "material feels",
            "chemical smell",
            "odor",
            "smell",
            "气味大",
            "材质差",
            "塑料感",
        ],
        "label": "材质/气味问题",
        "severity": "中",
        "improvement": "升级材质，增加散味处理，选用环保无毒材料",
    },
    "customer_service": {
        "keywords": [
            "customer service",
            "refund",
            "return",
            "no response",
            "not helpful",
            "wouldn't help",
            "客服差",
            "不退货",
        ],
        "label": "售后/客服问题",
        "severity": "低",
        "improvement": "加强客服响应，优化退换货流程",
    },
    "packaging": {
        "keywords": [
            "packaging",
            "damaged in",
            "box was",
            "包装破损",
            "包装简陋",
            "收到时已",
        ],
        "label": "包装/物流损坏",
        "severity": "低",
        "improvement": "升级包装材料，增加缓冲层，使用更坚固的外箱",
    },
    "color_appearance": {
        "keywords": [
            "color different",
            "not the color",
            "looks nothing",
            "different from picture",
            "颜色不对",
            "色差",
            "与图片不符",
        ],
        "label": "色差/外观不符",
        "severity": "中",
        "improvement": "优化产品拍摄，多角度展示，标注色差提示",
    },
    "safety": {
        "keywords": [
            "dangerous",
            "hazard",
            "sharp",
            "choking",
            "burn",
            "shock",
            "fire",
            "安全",
            "危险",
        ],
        "label": "安全隐患",
        "severity": "高",
        "improvement": "立即排查安全隐患，增加安全警告标识，必要时召回",
    },
}

# 停用词（分析时过滤）
STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "as",
    "is",
    "was",
    "are",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "i",
    "me",
    "my",
    "we",
    "our",
    "you",
    "your",
    "it",
    "its",
    "they",
    "them",
    "their",
    "this",
    "that",
    "these",
    "those",
    "not",
    "no",
    "very",
    "so",
    "too",
    "just",
    "really",
    "also",
    "even",
    "still",
    "only",
    "very",
    "much",
    "more",
    "产品",
    "这个",
    "那个",
    "非常",
    "很",
    "不",
    "了",
    "的",
}


class ReviewAnalyzer:
    """差评分析器 — 规则驱动的关键词聚类"""

    def analyze_product(self, asin: str, title: str, reviews: List[ReviewItem]) -> ReviewAnalysis:
        """对单个产品的差评进行分析"""
        if not reviews:
            return self._empty_result(asin, title)

        total = len(reviews)
        negative = [r for r in reviews if r.rating <= 3.0]
        neg_count = len(negative)
        avg_rating = sum(r.rating for r in reviews) / total if total > 0 else 0

        if neg_count == 0:
            return ReviewAnalysis(
                asin=asin,
                title=title,
                total_reviews_analyzed=total,
                negative_review_count=0,
                average_rating=avg_rating,
                clusters=[],
                top_defect="无明显缺陷",
                overall_rating="优",
                actionable_advice="产品评价良好，继续保持",
            )

        # 提取差评文本
        texts = [r.text for r in negative]

        # 关键词匹配 → 投诉聚类
        clusters = self._cluster_complaints(texts)

        # 核心缺陷
        if clusters:
            top_cluster = max(clusters, key=lambda c: c.count)
            top_defect = f"{top_cluster.label}（出现{top_cluster.count}次）"
        else:
            top_defect = "未识别到明显聚类"

        # 综合品控评价
        overall = self._overall_rating(clusters, avg_rating, neg_count, total)

        # 可落地建议
        advice = self._actionable_advice(clusters)

        return ReviewAnalysis(
            asin=asin,
            title=title,
            total_reviews_analyzed=total,
            negative_review_count=neg_count,
            average_rating=avg_rating,
            clusters=clusters,
            top_defect=top_defect,
            overall_rating=overall,
            actionable_advice=advice,
        )

    def _cluster_complaints(self, texts: List[str]) -> List[ComplaintCluster]:
        """基于关键词匹配的投诉聚类"""
        cluster_scores: Dict[str, dict] = {}

        for defect_id, config in DEFECT_KEYWORDS.items():
            count = 0
            matched_reviews = []

            for text in texts:
                text_lower = text.lower()
                for kw in config["keywords"]:
                    if kw.lower() in text_lower:
                        count += 1
                        # 截取关键词附近的上下文作为示例
                        idx = text_lower.find(kw.lower())
                        start = max(0, idx - 30)
                        end = min(len(text), idx + len(kw) + 60)
                        snippet = text[start:end].strip()
                        if len(snippet) > 20:
                            matched_reviews.append(snippet)
                        break  # 每篇评论只计一次

            if count > 0:
                cluster_scores[defect_id] = {
                    "label": config["label"],
                    "keywords": config["keywords"][:5],
                    "count": count,
                    "severity": config["severity"],
                    "examples": matched_reviews[:5],
                    "improvement": config["improvement"],
                }

        # 按出现次数排序
        sorted_clusters = sorted(
            cluster_scores.values(),
            key=lambda x: x["count"],
            reverse=True,
        )

        return [
            ComplaintCluster(
                label=c["label"],
                keywords=c["keywords"],
                count=c["count"],
                severity=c["severity"],
                example_reviews=c["examples"][:3],
                improvement_suggestion=c["improvement"],
            )
            for c in sorted_clusters
        ]

    def _overall_rating(
        self,
        clusters: List[ComplaintCluster],
        avg_rating: float,
        neg_count: int,
        total: int,
    ) -> str:
        """综合品控评价"""
        # 检查是否有高严重度问题
        high_sev = sum(c.count for c in clusters if c.severity == "高")
        neg_ratio = neg_count / total if total > 0 else 0

        if high_sev >= 5 or neg_ratio > 0.5:
            return "差"
        elif high_sev >= 2 or neg_ratio > 0.3:
            return "中"
        elif avg_rating >= 4.0 and neg_ratio < 0.1:
            return "优"
        elif avg_rating >= 3.5:
            return "良"
        else:
            return "中"

    def _actionable_advice(self, clusters: List[ComplaintCluster]) -> str:
        """生成可落地的改进建议"""
        if not clusters:
            return "基于当前数据未发现明显改进点"

        # 按严重度排序
        severity_order = {"高": 0, "中": 1, "低": 2}
        sorted_clusters = sorted(
            clusters,
            key=lambda c: (severity_order.get(c.severity, 9), -c.count),
        )

        top3 = sorted_clusters[:3]
        parts = []
        for c in top3:
            pct = (c.count / max(sum(x.count for x in clusters), 1)) * 100
            parts.append(f"【{c.label}】占投诉{pct:.0f}%: {c.improvement_suggestion}")
        return "；".join(parts)

    def _empty_result(self, asin: str, title: str) -> ReviewAnalysis:
        return ReviewAnalysis(
            asin=asin,
            title=title,
            total_reviews_analyzed=0,
            negative_review_count=0,
            average_rating=0,
            clusters=[],
            top_defect="无数据",
            overall_rating="未知",
            actionable_advice="",
        )

    # ─── 批量分析 ────────────────────────────────────

    def analyze_batch(
        self,
        products_reviews: Dict[str, Tuple[str, List[ReviewItem]]],
        category: str = "",
    ) -> ReviewAnalysisBatch:
        """批量分析多个产品的差评，并提取跨产品共性问题"""
        results = []
        all_cluster_labels: List[str] = []

        for asin, (title, reviews) in products_reviews.items():
            if not reviews:
                continue
            analysis = self.analyze_product(asin, title, reviews)
            results.append(analysis)
            for c in analysis.clusters:
                all_cluster_labels.extend([c.label] * c.count)

        # 跨产品共性
        if all_cluster_labels:
            counter = Counter(all_cluster_labels)
            total_mentions = sum(counter.values())
            cross_cutting = [
                f"{label}（{count}次，占{count/total_mentions*100:.0f}%）"
                for label, count in counter.most_common(5)
            ]
        else:
            cross_cutting = []

        # 品类机会判断
        opportunity = self._category_opportunity(results, cross_cutting)

        return ReviewAnalysisBatch(
            category=category,
            products_analyzed=len(results),
            results=results,
            cross_cutting_defects=cross_cutting,
            category_opportunity_note=opportunity,
        )

    def _category_opportunity(
        self,
        analyses: List[ReviewAnalysis],
        cross_cutting: List[str],
    ) -> str:
        """基于差评数据判断品类机会"""
        if not analyses:
            return "无数据"

        # 计算平均品质分
        good_count = sum(1 for a in analyses if a.overall_rating in ("优", "良"))
        bad_count = sum(1 for a in analyses if a.overall_rating in ("中", "差"))
        total = len(analyses)

        if bad_count > total * 0.5:
            return (
                "⚠️ 超过一半的产品品控评价为中/差，"
                "说明该类目存在普遍的质量问题，"
                "如果能针对性解决以下共性问题，将是很好的切入机会: " + "；".join(cross_cutting[:3])
            )
        elif good_count > total * 0.7:
            return (
                "✅ 该类目产品整体品控较好，差评集中在个别品牌，"
                "新品需在材料和工艺上做到同等或更优水平"
            )
        else:
            return (
                "📊 该类目品控水平分化，部分产品有明确的改进空间，"
                "建议重点参考差评聚类中的高频问题做产品迭代"
            )
