"""
差评分析数据模型 — 评论 / 聚类 / 分析结果
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ReviewItem:
    """单条评论"""
    asin: str
    rating: float                 # 评分 (1-5)
    title: str                    # 评论标题
    text: str                     # 评论正文
    date: str                     # 评论日期
    reviewer: str                 # 评论者
    verified_purchase: bool       # 是否Verified Purchase

    def to_dict(self) -> dict:
        return {
            "asin": self.asin,
            "rating": self.rating,
            "title": self.title[:120],
            "text": self.text[:500],
            "date": self.date,
            "reviewer": self.reviewer[:20],
            "verified_purchase": self.verified_purchase,
        }


@dataclass
class ComplaintCluster:
    """投诉聚类"""
    label: str                    # 聚类标签，如 "质量缺陷"
    keywords: List[str]           # 关键词列表
    count: int                    # 提及次数
    severity: str                 # 严重程度：高/中/低
    example_reviews: List[str]    # 示例评论（原文片段）
    improvement_suggestion: str   # 改进建议

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "keywords": self.keywords,
            "count": self.count,
            "severity": self.severity,
            "example_reviews": [r[:200] for r in self.example_reviews[:3]],
            "improvement_suggestion": self.improvement_suggestion,
        }


@dataclass
class ReviewAnalysis:
    """差评分析结果（针对一个 ASIN）"""
    asin: str
    title: str                    # 产品标题
    total_reviews_analyzed: int   # 分析的评论总数
    negative_review_count: int    # 差评数（1-3星）
    average_rating: float         # 评论平均分
    clusters: List[ComplaintCluster]  # 投诉聚类
    top_defect: str               # 核心缺陷一句话总结
    overall_rating: str           # 综合品控评价：优/良/中/差
    actionable_advice: str        # 可落地的改进建议

    def to_dict(self) -> dict:
        return {
            "asin": self.asin,
            "title": self.title,
            "total_reviews_analyzed": self.total_reviews_analyzed,
            "negative_review_count": self.negative_review_count,
            "average_rating": round(self.average_rating, 2),
            "clusters": [c.to_dict() for c in self.clusters],
            "top_defect": self.top_defect,
            "overall_rating": self.overall_rating,
            "actionable_advice": self.actionable_advice,
        }


@dataclass
class ReviewAnalysisBatch:
    """批量差评分析结果"""
    category: str
    products_analyzed: int
    results: List[ReviewAnalysis]
    cross_cutting_defects: List[str]       # 跨产品的共性问题
    category_opportunity_note: str         # 基于差评的品类机会判断

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "products_analyzed": self.products_analyzed,
            "results": [r.to_dict() for r in self.results],
            "cross_cutting_defects": self.cross_cutting_defects,
            "category_opportunity_note": self.category_opportunity_note,
        }
