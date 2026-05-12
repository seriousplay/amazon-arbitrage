"""
Matcher Module

跨语言模糊匹配核心功能

架构：
- synonyms.py: SynonymManager - 同义词词典管理器
- normalizer.py: TextNormalizer - 文本标准化器
- matcher.py: FuzzyMatcher - 核心匹配算法
"""

from .synonyms import SynonymManager
from .normalizer import TextNormalizer
from .matcher import FuzzyMatcher, MatchResult

__all__ = ["FuzzyMatcher", "MatchResult", "SynonymManager", "TextNormalizer"]
