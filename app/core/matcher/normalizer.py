"""
TextNormalizer - 文本标准化器

职责：
- 英文词形还原（复数→单数、动词→原形）
- 中文分词（使用 jieba）
- 多语言混合文本处理
- 文本清洗和预处理
"""

import re
from typing import List, Set, Tuple

import jieba

from app.core.matcher.synonyms import SynonymManager


class TextNormalizer:
    """文本标准化器"""

    def __init__(self, synonym_manager: SynonymManager = None):
        """
        初始化 TextNormalizer

        Args:
            synonym_manager: SynonymManager 实例（可选）
        """
        self.synonyms = synonym_manager or SynonymManager()
        self.custom_terms = [
            "耐咬",
            "强力咀嚼",
            "发声器",
            "自动饮水",
            "自动饮水器",
            "不锈钢",
            "活水器",
            "猫砂盆",
            "带盖",
            "封闭式",
            "大型犬",
            "小型犬",
            "中型犬",
            "宠物床",
            "猫爬架",
            "猫抓板",
            "狗咬胶",
            "磨牙棒",
            "宠物食碗",
            "航空箱",
            "胸背带",
            "牵引绳",
            "宠物包",
            "尿垫",
            "除臭",
            "宠物",
            "食碗",
            "碗",
            "饮水",
            "发声",
            "球",
            "猫",
            "狗",
            "互动",
            "娱乐",
            "自动",
            "智能",
            "感应",
        ]

        # 注册 jieba 专有词汇
        for term in self.custom_terms:
            jieba.add_word(term, freq=1000, tag="n")

    def normalize_text(self, text: str) -> str:
        """
        文本标准化：中英文混合 + 宠物用品同义词扩展

        策略：
        1. 英文词 → 基本形式（词形还原）
        2. 英文词 → 中文同义词
        3. 保留有意义的中文词
        4. 过滤停用词

        Args:
            text: 输入文本（英文或中文）

        Returns:
            标准化后的文本
        """
        if not text:
            return ""

        text = text.lower().strip()

        # 分词：英文词、数字、中文块
        tokens = re.findall(r"[a-zA-Z]+|\d+\.?\d*|[^a-zA-Z\s]+", text)

        keywords = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if re.match(r"^[a-zA-Z]+$", token):  # 英文词
                # 词形还原
                base_form = self.synonyms.get_base_form(token)

                # 优先匹配词组（2-gram）
                if i + 1 < len(tokens) and re.match(r"^[a-zA-Z]+$", tokens[i + 1]):
                    bigram = f"{base_form} {tokens[i+1]}"
                    if bigram in self.synonyms.pet_synonyms:
                        keywords.extend(self.synonyms.pet_synonyms[bigram].split())
                        i += 2
                        continue

                # 单个词匹配
                if base_form in self.synonyms.pet_synonyms:
                    keywords.extend(self.synonyms.pet_synonyms[base_form].split())
                elif token in self.synonyms.pet_synonyms:
                    keywords.extend(self.synonyms.pet_synonyms[token].split())
                else:
                    # 保留有意义的英文词（长度>2，非停用词）
                    if len(token) > 2 and not self.synonyms.is_stop_word(token, "en"):
                        keywords.append(token)

                i += 1
            elif re.match(r"^[^a-zA-Z\s]+$", token):  # 中文/数字/符号
                # 检查是否是有意义的中文词
                if not self.synonyms.is_stop_word(token, "zh"):
                    # 使用 jieba 分词
                    seg_list = jieba.lcut(token)
                    keywords.extend(
                        [
                            w
                            for w in seg_list
                            if len(w.strip()) > 0 and not self.synonyms.is_stop_word(w, "zh")
                        ]
                    )
                i += 1
            else:
                i += 1

        # 应用语义归一化
        normalized = [self.synonyms.normalize(w) for w in keywords]

        # 去重并保持顺序
        seen = set()
        result = []
        for w in normalized:
            if w not in seen:
                seen.add(w)
                result.append(w)

        return " ".join(result)

    def extract_keywords(self, text: str, max_keywords: int = 10) -> List[str]:
        """
        提取关键词

        Args:
            text: 输入文本
            max_keywords: 最大关键词数

        Returns:
            关键词列表
        """
        normalized = self.normalize_text(text)
        return normalized.split()[:max_keywords]

    def tokenize(self, text: str) -> List[str]:
        """
        分词（支持中英文混合）

        Args:
            text: 输入文本

        Returns:
            词元列表
        """
        # 简单的分词实现
        tokens = re.findall(r"[a-zA-Z]+|\d+\.?\d*|[一-鿿]+|[^\x00-\x7F]+", text)
        return [t.strip() for t in tokens if t.strip()]

    def is_similar(self, text1: str, text2: str, threshold: float = 0.7) -> bool:
        """
        判断两个文本是否相似

        Args:
            text1: 文本1
            text2: 文本2
            threshold: 相似度阈值

        Returns:
            是否相似
        """
        norm1 = self.normalize_text(text1)
        norm2 = self.normalize_text(text2)

        # Jaccard 相似度
        set1 = set(norm1.split())
        set2 = set(norm2.split())

        if not set1 or not set2:
            return False

        intersection = set1 & set2
        union = set1 | set2
        jaccard = len(intersection) / len(union)

        return jaccard >= threshold
