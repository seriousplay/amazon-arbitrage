"""
匹配评分引擎测试
"""
import pytest
from unittest.mock import MagicMock

from app.models.product import AmazonProduct, AlibabaProduct
from app.core.scorer import MatchScorer


@pytest.fixture
def config():
    c = MagicMock()
    c.PRICE_DIFF_WEIGHT = 0.4
    c.SALES_WEIGHT = 0.3
    c.RATING_WEIGHT = 0.2
    c.COMPETITION_WEIGHT = 0.1
    return c


@pytest.fixture
def scorer(config):
    return MatchScorer(config)


class TestMatchScorer:
    def test_high_profit_score(self, scorer):
        """高价差 + 高销量 + 高评分 → 高分"""
        amazon = AmazonProduct(
            asin="B001", title="Premium Dog Food", category="Dogs",
            rank=50, price=50.0, rating=4.8, review_count=5000,
        )
        alibaba = AlibabaProduct(
            item_id="100", title="Dog Food OEM", price=30.0,
            min_order_qty=100, matched_score=90.0,
        )
        result = scorer.score_match(amazon, alibaba)
        assert result.score >= 70
        assert result.confidence in ("high", "medium")

    def test_negative_margin(self, scorer):
        """1688 成本高于 Amazon 售价 → 不推荐"""
        amazon = AmazonProduct(
            asin="B002", title="Cheap Toy", category="Dogs",
            rank=500, price=5.0, rating=3.0, review_count=10,
        )
        alibaba = AlibabaProduct(
            item_id="200", title="Expensive OEM", price=100.0,
            min_order_qty=10, matched_score=50.0,
        )
        result = scorer.score_match(amazon, alibaba)
        assert result.price_diff_usd < 0
        assert "价差为负" in result.recommendation
        assert result.confidence == "low"

    def test_no_price_data(self, scorer):
        """Amazon 商品无价格 → 低分"""
        amazon = AmazonProduct(
            asin="B003", title="No Price Item", category="Cats",
            rank=100,
        )
        alibaba = AlibabaProduct(
            item_id="300", title="Supplier Item", price=10.0,
            min_order_qty=5, matched_score=70.0,
        )
        result = scorer.score_match(amazon, alibaba)
        assert result.score < 60
        assert result.confidence == "low"

    def test_high_review_sales_score(self, scorer):
        """高评论数 → 销量分 >= 20"""
        amazon = AmazonProduct(
            asin="B004", title="Best Seller", category="Dogs",
            rank=1, price=30.0, rating=4.5, review_count=15000,
        )
        alibaba = AlibabaProduct(
            item_id="400", title="OEM Best Seller", price=15.0,
            min_order_qty=50, matched_score=85.0,
        )
        result = scorer.score_match(amazon, alibaba)
        assert result.score >= 60

    def test_score_bounds(self, scorer):
        """分数在 0-100 范围内"""
        amazon = AmazonProduct(asin="B005", title="T", category="C", rank=1, price=100.0, rating=5.0, review_count=50000)
        alibaba = AlibabaProduct(item_id="500", title="T", price=1.0, min_order_qty=1, matched_score=100.0)
        result = scorer.score_match(amazon, alibaba)
        assert 0 <= result.score <= 100
