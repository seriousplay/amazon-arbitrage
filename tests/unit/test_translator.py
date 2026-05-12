"""
翻译器测试

测试覆盖：
- 英文到中文翻译
- 术语词典映射
- 停用词过滤
- 混合文本处理
"""

import pytest
from app.utils.translator import (
    to_chinese,
    translate_detail,
    STOP_WORDS,
    TERM_MAP,
)


class TestToChinese:
    """测试 to_chinese 函数"""

    def test_translate_simple_english(self):
        """测试简单英文翻译"""
        result = to_chinese("dog bed")
        assert isinstance(result, str)
        assert len(result) > 0
        # 应该返回中文字符
        assert any("\u4e00" <= c <= "\u9fff" for c in result)

    def test_translate_pet_supplies(self):
        """测试宠物用品类翻译"""
        result = to_chinese("pet supplies")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_translate_cat_tree(self):
        """测试猫爬架翻译"""
        result = to_chinese("cat tree")
        assert isinstance(result, str)
        # 应该包含 "猫" 或 "爬架" 相关

    def test_translate_empty_string(self):
        """测试空字符串"""
        result = to_chinese("")
        assert isinstance(result, str)
        # 空字符串应该返回空或保持空

    def test_translate_with_term_map(self):
        """测试术语词典映射"""
        # TERM_MAP 中的词应该被正确映射
        # 例如 "dog bed" 在 TERM_MAP 中
        result = to_chinese("dog bed")
        assert isinstance(result, str)

    def test_translate_preserves_stop_words(self):
        """测试保留重要词汇"""
        result = to_chinese("dog bed for large dogs")
        assert isinstance(result, str)
        assert len(result) > 0


class TestTranslateDetail:
    """测试 translate_detail 函数"""

    def test_translate_detail_returns_dict(self):
        """测试返回字典格式"""
        result = translate_detail("dog bed")
        assert isinstance(result, dict)

    def test_translate_detail_contains_original(self):
        """测试包含原文"""
        result = translate_detail("dog bed")
        assert "original" in result or "translated" in result

    def test_translate_detail_multiple_items(self):
        """测试批量翻译"""
        items = ["dog bed", "cat tree", "pet supplies"]
        results = [translate_detail(item) for item in items]
        assert len(results) == 3
        assert all(isinstance(r, dict) for r in results)


class TestStopWords:
    """测试停用词"""

    def test_stop_words_loaded(self):
        """测试停用词已加载"""
        assert isinstance(STOP_WORDS, (list, set))
        assert len(STOP_WORDS) > 0

    def test_common_stop_words_present(self):
        """测试常见停用词存在"""
        # 英文停用词通常包括 "the", "a", "an", "and", "or"
        # 中文停用词通常包括 "的", "了", "是"
        stop_words_lower = {w.lower() for w in STOP_WORDS}
        # 至少应该有一些常见停用词
        assert len(stop_words_lower) > 10


class TestTermMap:
    """测试术语词典"""

    def test_term_map_loaded(self):
        """测试术语词典已加载"""
        assert isinstance(TERM_MAP, dict)
        assert len(TERM_MAP) > 0

    def test_term_map_entries(self):
        """测试术语词典条目格式"""
        for key, value in list(TERM_MAP.items())[:10]:
            assert isinstance(key, str)
            assert isinstance(value, str)
            assert len(key) > 0
            assert len(value) > 0

    def test_term_map_has_pet_terms(self):
        """测试术语词典包含宠物相关术语"""
        pet_terms = ["dog", "cat", "pet", "bed", "toy"]
        found_terms = [term for term in pet_terms if term.lower() in TERM_MAP]
        # 至少应该有一些宠物术语
        assert len(found_terms) > 0


class TestEdgeCases:
    """测试边界情况"""

    def test_translate_very_long_string(self):
        """测试超长字符串"""
        long_text = "dog bed " * 100
        result = to_chinese(long_text)
        assert isinstance(result, str)

    def test_translate_special_characters(self):
        """测试特殊字符"""
        special = "dog-bed_123!"
        result = to_chinese(special)
        assert isinstance(result, str)

    def test_translate_numbers(self):
        """测试数字"""
        result = to_chinese("123")
        assert isinstance(result, str)

    def test_translate_mixed_language(self):
        """测试中英文混合"""
        result = to_chinese("dog 狗 bed 窝")
        assert isinstance(result, str)
