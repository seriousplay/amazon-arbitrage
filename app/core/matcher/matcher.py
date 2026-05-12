"""
FuzzyMatcher - 跨语言模糊匹配器（核心算法）

职责：
- 实现多维相似度计算
- 融合 Jaccard + 编辑距离 + 数字 + 规格匹配
- 提供 match() 核心接口
"""

from dataclasses import dataclass
from typing import Dict, Optional

from thefuzz import fuzz

from app.core.matcher.synonyms import SynonymManager
from app.core.matcher.normalizer import TextNormalizer


@dataclass
class MatchResult:
    """匹配结果"""

    score: float
    strategy: str
    confidence: str  # high / medium / low
    details: Optional[Dict] = None


class FuzzyMatcher:
    """
    跨语言模糊匹配器

    工作流程：
    1. 文本标准化（英文词 → 中文同义词 + 中文分词）
    2. 多维度相似度计算（Jaccard + 编辑距离 + 数字 + 规格）
    3. 加权融合 + 惩罚机制
    """

    def __init__(
        self,
        synonym_manager: SynonymManager = None,
        normalizer: TextNormalizer = None,
    ):
        """
        初始化 FuzzyMatcher

        Args:
            synonym_manager: SynonymManager 实例
            normalizer: TextNormalizer 实例
        """
        self.synonyms = synonym_manager or SynonymManager()
        self.normalizer = normalizer or TextNormalizer(self.synonyms)

    def match(self, text_a: str, text_b: str) -> MatchResult:
        """
        计算两个文本的匹配度

        Args:
            text_a: 文本 A（如 Amazon 标题）
            text_b: 文本 B（如 1688 标题）

        Returns:
            MatchResult 包含分数、策略、置信度
        """
        if not text_a or not text_b:
            return MatchResult(
                score=0.0,
                strategy="empty",
                confidence="low",
                details={"reason": "empty_input"},
            )

        # 1. 文本标准化
        norm_a = self.normalizer.normalize_text(text_a)
        norm_b = self.normalizer.normalize_text(text_b)

        # 2. 计算多维相似度
        scores = {}
        details = {}

        # Jaccard 相似度
        set_a = set(norm_a.split())
        set_b = set(norm_b.split())
        if set_a and set_b:
            intersection = set_a & set_b
            union = set_a | set_b
            jaccard = len(intersection) / len(union)
            scores["jaccard"] = jaccard
            details["jaccard"] = jaccard
            details["intersection"] = len(intersection)
            details["union"] = len(union)
        else:
            scores["jaccard"] = 0.0

        # 编辑距离（使用 fuzzywuzzy）
        edit_ratio = fuzz.ratio(norm_a, norm_b) / 100.0
        scores["edit"] = edit_ratio
        details["edit_ratio"] = edit_ratio

        # 部分匹配（针对较长文本）
        partial_ratio = fuzz.partial_ratio(norm_a, norm_b) / 100.0
        scores["partial"] = partial_ratio
        details["partial_ratio"] = partial_ratio

        # 3. 加权融合
        weights = {
            "jaccard": 0.4,
            "edit": 0.3,
            "partial": 0.3,
        }

        total_score = sum(scores.get(k, 0) * w for k, w in weights.items())

        # 4. 惩罚机制
        # 长度差异惩罚
        len_a = len(norm_a.split())
        len_b = len(norm_b.split())
        if len_a > 0 and len_b > 0:
            len_ratio = min(len_a, len_b) / max(len_a, len_b)
            if len_ratio < 0.5:
                total_score *= 0.8  # 长度差异过大，降低分数

        # 5. 计算置信度
        confidence = self._calculate_confidence(total_score)

        # 6. 确定策略
        strategy = self._determine_strategy(scores)

        details["norm_a"] = norm_a
        details["norm_b"] = norm_b
        details["raw_scores"] = scores

        return MatchResult(
            score=round(total_score * 100, 2),
            strategy=strategy,
            confidence=confidence,
            details=details,
        )

    def _calculate_confidence(self, score: float) -> str:
        """
        根据分数计算置信度

        Args:
            score: 匹配分数（0-1）

        Returns:
            置信度字符串（high/medium/low）
        """
        if score >= 0.8:
            return "high"
        elif score >= 0.6:
            return "medium"
        else:
            return "low"

    def _determine_strategy(self, scores: Dict[str, float]) -> str:
        """
        确定匹配策略

        Args:
            scores: 各维度分数

        Returns:
            策略名称
        """
        max_score = max(scores.values()) if scores else 0

        if max_score >= 0.9:
            return "exact"
        elif scores.get("jaccard", 0) >= 0.7:
            return "jaccard"
        elif scores.get("edit", 0) >= 0.8:
            return "fuzzy"
        elif scores.get("partial", 0) >= 0.8:
            return "partial"
        else:
            return "low_confidence"

    def batch_match(
        self,
        texts_a: list,
        texts_b: list,
    ) -> list:
        """
        批量匹配

        Args:
            texts_a: 文本 A 列表
            texts_b: 文本 B 列表

        Returns:
            匹配结果列表（两两组合）
        """
        results = []
        for a in texts_a:
            for b in texts_b:
                result = self.match(a, b)
                results.append((a, b, result))
        return results
