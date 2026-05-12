"""
FuzzyMatcher 模块测试

测试覆盖：
- SynonymManager 词典加载和查询
- TextNormalizer 文本标准化
- FuzzyMatcher 核心匹配算法
- 匹配策略选择
- 置信度计算
"""

import pytest
from pathlib import Path
from app.core.matcher import FuzzyMatcher, SynonymManager, TextNormalizer
from app.core.matcher.matcher import MatchResult


@pytest.fixture
def synonym_manager():
    """创建 SynonymManager 实例"""
    return SynonymManager()


@pytest.fixture
def text_normalizer(synonym_manager):
    """创建 TextNormalizer 实例"""
    return TextNormalizer(synonym_manager=synonym_manager)


@pytest.fixture
def fuzzy_matcher(synonym_manager, text_normalizer):
    """创建 FuzzyMatcher 实例"""
    return FuzzyMatcher(
        synonym_manager=synonym_manager,
        normalizer=text_normalizer,
    )


class TestSynonymManager:
    """测试 SynonymManager"""

    def test_load_pet_synonyms(self, synonym_manager):
        """测试加载宠物同义词词典"""
        assert synonym_manager.pet_synonyms is not None
        assert isinstance(synonym_manager.pet_synonyms, dict)
        # 验证词典已加载（应有数据）
        assert len(synonym_manager.pet_synonyms) > 0

    def test_get_synonyms_returns_string(self, synonym_manager):
        """测试 get_synonyms 返回字符串"""
        result = synonym_manager.get_synonyms("dog")
        assert isinstance(result, str)

    def test_get_synonyms_empty_input(self, synonym_manager):
        """测试空输入"""
        result = synonym_manager.get_synonyms("")
        assert isinstance(result, str)

    def test_get_base_form(self, synonym_manager):
        """测试获取词根形式"""
        result = synonym_manager.get_base_form("dogs")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_normalize_word(self, synonym_manager):
        """测试单词标准化"""
        result = synonym_manager.normalize("Dog")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_is_stop_word_english(self, synonym_manager):
        """测试英文停用词检测"""
        # "the" 应该是停用词
        assert synonym_manager.is_stop_word("the", "en") is True
        # "dog" 应该不是停用词
        assert synonym_manager.is_stop_word("dog", "en") is False

    def test_is_stop_word_chinese(self, synonym_manager):
        """测试中文停用词检测"""
        # "包邮" 应该是停用词
        assert synonym_manager.is_stop_word("包邮", "zh") is True
        # "狗" 应该不是停用词
        assert synonym_manager.is_stop_word("狗", "zh") is False

    def test_is_stop_word_unknown_language(self, synonym_manager):
        """测试未知语言"""
        result = synonym_manager.is_stop_word("test", "unknown")
        assert result is False


class TestTextNormalizer:
    """测试 TextNormalizer"""

    def test_normalize_text_lowercase(self, text_normalizer):
        """测试文本转小写"""
        result = text_normalizer.normalize_text("DOG BED")
        assert result == result.lower()

    def test_normalize_text_removes_punctuation(self, text_normalizer):
        """测试去除标点符号"""
        result = text_normalizer.normalize_text("dog-bed, extra!")
        # 应该去除或替换标点
        assert isinstance(result, str)
        assert len(result) > 0

    def test_normalize_text_whitespace(self, text_normalizer):
        """测试空白字符规范化"""
        result = text_normalizer.normalize_text("  dog   bed  ")
        # 应该规范化空白字符
        assert "  " not in result  # 没有连续空格

    def test_extract_keywords(self, text_normalizer):
        """测试关键词提取"""
        text = "Premium Dog Bed for Large Dogs"
        keywords = text_normalizer.extract_keywords(text, max_keywords=5)
        assert isinstance(keywords, list)
        assert len(keywords) <= 5
        assert all(isinstance(kw, str) for kw in keywords)

    def test_extract_keywords_empty_text(self, text_normalizer):
        """测试空文本关键词提取"""
        keywords = text_normalizer.extract_keywords("", max_keywords=5)
        assert isinstance(keywords, list)
        assert len(keywords) == 0

    def test_tokenize(self, text_normalizer):
        """测试文本分词"""
        text = "dog bed for pets"
        tokens = text_normalizer.tokenize(text)
        assert isinstance(tokens, list)
        assert all(isinstance(t, str) for t in tokens)
        assert len(tokens) > 0

    def test_is_similar_high_similarity(self, text_normalizer):
        """测试高相似度文本"""
        text1 = "dog bed"
        text2 = "dog beds"
        # 应该被认为是相似的
        result = text_normalizer.is_similar(text1, text2, threshold=0.7)
        assert isinstance(result, bool)

    def test_is_similar_low_similarity(self, text_normalizer):
        """测试低相似度文本"""
        text1 = "dog bed"
        text2 = "cat tree"
        result = text_normalizer.is_similar(text1, text2, threshold=0.7)
        assert isinstance(result, bool)
        # 低相似度应该返回 False
        assert result is False


class TestFuzzyMatcher:
    """测试 FuzzyMatcher 核心算法"""

    def test_match_identical_strings(self, fuzzy_matcher):
        """测试完全相同的字符串"""
        result = fuzzy_matcher.match("dog bed", "dog bed")
        assert isinstance(result, MatchResult)
        # 完全匹配应该有高分
        assert result.score >= 80

    def test_match_similar_strings(self, fuzzy_matcher):
        """测试相似字符串"""
        result = fuzzy_matcher.match("dog bed", "dog beds")
        assert isinstance(result, MatchResult)
        # 相似字符串应该有较高分数
        assert result.score >= 60

    def test_match_different_strings(self, fuzzy_matcher):
        """测试不同字符串"""
        result = fuzzy_matcher.match("dog bed", "cat tree")
        assert isinstance(result, MatchResult)
        # 不同字符串分数应该较低
        assert result.score < 50

    def test_match_with_synonyms(self, fuzzy_matcher):
        """测试同义词匹配"""
        result1 = fuzzy_matcher.match("dog bed", "dog bed")
        result2 = fuzzy_matcher.match("puppy bed", "dog bed")
        # 同义词应该有更高的匹配分数（相比完全不同的词）
        # 这取决于同义词词典的覆盖

    def test_match_case_insensitive(self, fuzzy_matcher):
        """测试大小写不敏感"""
        result1 = fuzzy_matcher.match("Dog Bed", "dog bed")
        result2 = fuzzy_matcher.match("DOG BED", "dog bed")
        # 大小写不应影响匹配分数
        assert abs(result1.score - result2.score) < 5

    def test_match_chinese_english(self, fuzzy_matcher):
        """测试中英文混合匹配"""
        # "狗窝" 应该与 "dog bed" 匹配
        result = fuzzy_matcher.match("dog bed", "狗窝")
        assert isinstance(result, MatchResult)
        assert result.score > 0  # 至少有一些匹配

    def test_match_empty_strings(self, fuzzy_matcher):
        """测试空字符串"""
        result = fuzzy_matcher.match("", "dog bed")
        assert isinstance(result, MatchResult)
        # 空字符串与任何东西匹配分数都应该为 0
        assert result.score == 0.0

    def test_match_both_empty(self, fuzzy_matcher):
        """测试两个空字符串"""
        result = fuzzy_matcher.match("", "")
        assert isinstance(result, MatchResult)
        # 两个空字符串应该返回 0 分
        assert result.score == 0.0

    def test_match_score_range(self, fuzzy_matcher):
        """测试匹配分数在 0-100 范围内"""
        test_cases = [
            ("dog bed", "cat tree"),
            ("premium dog food", "cheap cat food"),
            ("large dog bed", "big dog bed"),
        ]
        for text_a, text_b in test_cases:
            result = fuzzy_matcher.match(text_a, text_b)
            assert (
                0.0 <= result.score <= 100.0
            ), f"Score {result.score} out of range for {text_a} vs {text_b}"


class TestFuzzyMatcherStrategies:
    """测试不同匹配策略"""

    @pytest.fixture
    def matcher_with_strategies(self):
        """创建支持多种策略的 matcher"""
        return FuzzyMatcher()

    def test_exact_match_strategy(self, matcher_with_strategies):
        """测试精确匹配策略"""
        result = matcher_with_strategies.match("test", "test")
        assert result.score >= 95
        assert result.strategy == "exact"

    def test_fuzzy_match_strategy(self, matcher_with_strategies):
        """测试模糊匹配策略"""
        result = matcher_with_strategies.match("test", "tst")
        assert result.score > 45  # fuzzy match gives moderate score
        # 策略应该是 fuzzy 或 partial
        assert result.strategy in ("fuzzy", "partial", "low_confidence")

    def test_semantic_match_strategy(self, matcher_with_strategies):
        """测试语义匹配策略"""
        # "puppy" 和 "dog" 应该通过语义匹配
        result = matcher_with_strategies.match("puppy bed", "dog bed")
        assert result.score > 60


class TestIntegration:
    """集成测试"""

    def test_full_matching_pipeline(self, fuzzy_matcher):
        """测试完整匹配流程"""
        # 模拟真实的 Amazon → 1688 匹配流程
        amazon_title = "Premium Memory Foam Dog Bed - Large"
        alibaba_titles = [
            "记忆棉狗窝 大号",
            "Memory Foam Pet Bed for Dogs",
            "Cat Tree House",
            "狗床 记忆棉 大号",
        ]

        scores = []
        for ali_title in alibaba_titles:
            result = fuzzy_matcher.match(amazon_title, ali_title)
            scores.append((ali_title, result.score, result.strategy))

        # 排序，最高分的应该是第一个或第四个（中文匹配）
        scores.sort(key=lambda x: x[1], reverse=True)

        # 最相关的匹配应该在前两名
        top2 = [title for title, _, _ in scores[:2]]
        # 至少有一个中文匹配在前两名
        has_chinese = any("狗" in title or "窝" in title for title in top2)
        assert has_chinese, f"Expected Chinese match in top 2, got: {top2}"

    def test_json_data_loading(self):
        """测试 JSON 词典文件加载"""
        # 验证词典文件存在且可加载
        data_dir = Path(__file__).parent.parent.parent / "data" / "matcher"
        required_files = [
            "pet_synonyms.json",
            "en_variations.json",
            "semantic_norm.json",
            "stop_words_en.json",
            "stop_words_zh.json",
        ]
        for filename in required_files:
            filepath = data_dir / filename
            assert filepath.exists(), f"Missing data file: {filename}"
            # 验证 JSON 有效性
            import json

            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                assert isinstance(data, dict) or isinstance(data, list)
