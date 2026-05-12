"""
模型验证测试
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from app.models.product import AmazonProduct, AlibabaProduct, MatchResult


class TestAmazonProduct:
    def test_valid_product(self):
        p = AmazonProduct(
            asin="B00MW8G3YU",
            title="Dog Pads",
            category="Dogs",
            rank=100,
            price=29.99,
            rating=4.5,
            review_count=1000,
        )
        assert p.asin == "B00MW8G3YU"
        assert p.price == 29.99
        assert p.rating == 4.5

    def test_minimal_product(self):
        p = AmazonProduct(asin="B000000000", title="Test", category="Dogs", rank=500)
        assert p.price is None
        assert p.rating is None
        assert p.review_count is None
        assert p.is_prime is False

    def test_rank_bounds(self):
        with pytest.raises(ValidationError):
            AmazonProduct(asin="X", title="X", category="X", rank=0)
        with pytest.raises(ValidationError):
            AmazonProduct(asin="X", title="X", category="X", rank=2000000)

    def test_rating_bounds(self):
        with pytest.raises(ValidationError):
            AmazonProduct(asin="X", title="X", category="X", rank=10, rating=6.0)

    def test_scraped_at_auto(self):
        p = AmazonProduct(asin="B000000000", title="T", category="C", rank=1)
        assert isinstance(p.scraped_at, datetime)


class TestAlibabaProduct:
    def test_valid_product(self):
        p = AlibabaProduct(
            item_id="12345",
            title="Pet Toy",
            price=5.0,
            min_order_qty=10,
            supplier="Factory A",
            matched_score=85.0,
        )
        assert p.item_id == "12345"
        assert p.moq == 10  # property alias

    def test_defaults(self):
        p = AlibabaProduct(item_id="1", title="X", price=1.0, min_order_qty=1, matched_score=50.0)
        assert p.supplier == "Unknown"

    def test_price_non_negative(self):
        with pytest.raises(ValidationError):
            AlibabaProduct(item_id="1", title="X", price=-1.0, min_order_qty=1, matched_score=50.0)

    def test_moq_property(self):
        p = AlibabaProduct(item_id="1", title="X", price=1.0, min_order_qty=5, matched_score=50.0)
        assert p.moq == 5
        assert p.min_order_qty == 5


class TestMatchResult:
    def test_result_creation(self):
        amazon = AmazonProduct(asin="A1", title="T1", category="C", rank=10, price=30.0)
        alibaba = AlibabaProduct(
            item_id="1", title="T2", price=5.0, min_order_qty=10, matched_score=80.0
        )
        r = MatchResult(
            amazon=amazon,
            alibaba=alibaba,
            score=75.0,
            price_diff_usd=15.0,
            estimated_profit_margin=50.0,
            total_cost_usd=57.5,
            confidence="medium",
            recommendation="good",
        )
        assert r.score == 75.0
        assert r.confidence_level == "medium"

    def test_confidence_high(self):
        amazon = AmazonProduct(asin="A1", title="T", category="C", rank=1, price=100.0)
        alibaba = AlibabaProduct(
            item_id="1", title="T", price=1.0, min_order_qty=1, matched_score=90.0
        )
        r = MatchResult(
            amazon=amazon,
            alibaba=alibaba,
            score=90.0,
            price_diff_usd=80.0,
            estimated_profit_margin=80.0,
            total_cost_usd=20.0,
            confidence="high",
            recommendation="buy",
        )
        assert r.confidence_level == "high"

    def test_confidence_low(self):
        amazon = AmazonProduct(asin="A1", title="T", category="C", rank=1, price=10.0)
        alibaba = AlibabaProduct(
            item_id="1", title="T", price=1.0, min_order_qty=1, matched_score=10.0
        )
        r = MatchResult(
            amazon=amazon,
            alibaba=alibaba,
            score=30.0,
            price_diff_usd=2.0,
            estimated_profit_margin=20.0,
            total_cost_usd=8.0,
            confidence="low",
            recommendation="skip",
        )
        assert r.confidence_level == "low"
