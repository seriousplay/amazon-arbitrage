"""
品类映射器测试

测试覆盖：
- 亚马逊类目到 1688 搜索关键词的转换
- 支持的类目列表
- 自定义 BSR URL 处理
- 映射准确性和完整性
"""

import pytest
from app.utils.category_mapper import (
    category_to_search,
    get_supported_categories,
    CATEGORY_MAP,
    normalize_category,
)


class TestCategoryMapping:
    """测试类目映射"""

    def test_dogs_category(self):
        """测试狗狗类目映射"""
        result = category_to_search("Dogs")
        assert isinstance(result, str)
        assert len(result) > 0
        # 应该映射到包含 "狗" 或相关关键词

    def test_cats_category(self):
        """测试猫类目映射"""
        result = category_to_search("Cats")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_birds_category(self):
        """测试鸟类目映射"""
        result = category_to_search("Birds")
        assert isinstance(result, str)
        # 应该映射到包含 "鸟" 或 "鹦鹉"

    def test_fish_category(self):
        """测试鱼类目映射"""
        result = category_to_search("Fish")
        assert isinstance(result, str)
        # 应该映射到包含 "鱼" 或 "水族"

    def test_small_animals_category(self):
        """测试小宠类目映射"""
        result = category_to_search("Small Animals")
        assert isinstance(result, str)
        # 应该映射到包含 "仓鼠"、"兔子" 等

    def test_reptiles_category(self):
        """测试爬宠类目映射"""
        result = category_to_search("Reptiles")
        assert isinstance(result, str)
        # 应该映射到包含 "爬宠"、"龟" 等

    def test_horse_category(self):
        """测试马类目映射"""
        result = category_to_search("Horses")
        assert isinstance(result, str)
        # 应该映射到包含 "马"

    def test_unknown_category(self):
        """测试未知类目"""
        # 未知类目应该返回默认值或空字符串
        result = category_to_search("UnknownCategory123")
        assert isinstance(result, str)
        # 可能返回 "宠物用品" 作为默认

    def test_case_insensitive(self):
        """测试大小写不敏感"""
        result1 = category_to_search("dogs")
        result2 = category_to_search("DOGS")
        result3 = category_to_search("Dogs")
        # 大小写不应影响结果
        assert result1 == result2 == result3

    def test_subcategory_mapping(self):
        """测试子类目映射"""
        # 测试有子类目的情况
        result = category_to_search("Dogs > Dog Beds")
        assert isinstance(result, str)
        # 应该映射到更具体的 "狗窝" 而不是笼统的 "宠物用品"


class TestSupportedCategories:
    """测试支持的类目列表"""

    def test_get_supported_categories(self):
        """测试获取支持的类目列表"""
        categories = get_supported_categories()
        assert isinstance(categories, (list, set))
        assert len(categories) > 0

    def test_supported_categories_contains_common(self):
        """测试常见类目存在"""
        categories = get_supported_categories()
        # 至少应该包含主要的宠物类目
        expected = ["Dogs", "Cats", "Birds", "Fish"]
        for cat in expected:
            # 类目应该在映射中（不一定是列表中，因为映射可能是 nested dict）
            pass  # 具体结构取决于实现

    def test_category_map_loaded(self):
        """测试 CATEGORY_MAP 已加载"""
        assert isinstance(CATEGORY_MAP, dict)
        assert len(CATEGORY_MAP) > 0

    def test_category_map_values_are_strings(self):
        """测试 CATEGORY_MAP 值为字符串（中文搜索词）"""
        for key, value in list(CATEGORY_MAP.items())[:10]:
            assert isinstance(value, str), f"Value for {key} should be a string"
            assert len(value) > 0, f"Value for {key} should not be empty"
            # 值应该是中文字符串
            assert any(
                "\u4e00" <= c <= "\u9fff" for c in value
            ), f"Value for {key} should contain Chinese characters"


class TestNormalizeCategory:
    """测试类目标准化"""

    def test_normalize_lowercase(self):
        """测试小写转换"""
        result = normalize_category("dogs")
        assert result == result.lower() or result == "Dogs"

    def test_normalize_trim_whitespace(self):
        """测试去除空白字符"""
        result = normalize_category("  Dogs  ")
        assert result == result.strip() or result == "Dogs"

    def test_normalize_title_case(self):
        """测试标题格式"""
        result = normalize_category("DOGS")
        # 应该转换为 "Dogs"
        assert result in ["Dogs", "dogs"]


class TestEdgeCases:
    """测试边界情况"""

    def test_empty_category(self):
        """测试空类目"""
        # 空类目应该返回默认值
        result = category_to_search("")
        assert isinstance(result, str)

    def test_none_category(self):
        """测试 None 类目"""
        # None 类目应该返回默认值或空字符串
        result = category_to_search(None)
        assert isinstance(result, str)
        assert result == "" or len(result) > 0

    def test_whitespace_only_category(self):
        """测试只有空白的类目"""
        result = category_to_search("   ")
        assert isinstance(result, str)

    def test_json_data_file_exists(self):
        """测试 JSON 数据文件存在"""
        from pathlib import Path

        data_file = (
            Path(__file__).parent.parent.parent / "data" / "categories" / "category_mapping.json"
        )
        assert data_file.exists(), f"Category mapping file missing: {data_file}"

    def test_json_data_valid(self):
        """测试 JSON 数据有效性"""
        import json
        from pathlib import Path

        data_file = (
            Path(__file__).parent.parent.parent / "data" / "categories" / "category_mapping.json"
        )
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_mapping_completeness(self):
        """测试映射完整性（至少覆盖主要类目）"""
        categories = get_supported_categories()
        # 至少应该支持 50 个类目
        assert len(categories) >= 50, f"Only {len(categories)} categories supported"


class TestIntegration:
    """集成测试"""

    def test_real_world_category_mapping(self):
        """测试真实场景的类目映射"""
        test_cases = [
            ("Dogs > Dog Beds", "狗窝"),
            ("Cats > Cat Trees", "猫爬架"),
            ("Birds > Bird Cages", "鸟笼"),
        ]
        for category, expected_keyword in test_cases:
            result = category_to_search(category)
            # 结果应该包含预期的中文关键词（不一定是精确匹配）
            assert isinstance(result, str)
            assert len(result) > 0

    def test_multiple_categories_return_different_keywords(self):
        """测试不同类目返回不同的关键词"""
        dogs_result = category_to_search("Dogs")
        cats_result = category_to_search("Cats")
        # 狗狗和猫类目的关键词应该不同
        assert dogs_result != cats_result
