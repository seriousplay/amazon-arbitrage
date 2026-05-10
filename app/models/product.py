"""
数据模型 — Amazon 和 1688 商品结构（Pydantic v2）
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class AmazonProduct(BaseModel):
    """Amazon 商品模型"""

    model_config = {
        "json_schema_extra": {
            "example": {
                "asin": "B00MW8G3YU",
                "title": "Amazon Basics Leak-Proof Dog and Puppy Potty Pads",
                "category": "Dogs",
                "rank": 123,
                "price": 29.99,
                "rating": 4.5,
                "review_count": 12580,
                "is_prime": True,
            }
        }
    }

    asin: str = Field(..., description="Amazon ASIN")
    title: str = Field(..., max_length=500, description="商品标题")
    category: str = Field(..., description="类目")
    rank: int = Field(..., ge=1, le=1000000, description="BSR 排名")
    price: Optional[float] = Field(None, ge=0, description="价格（美元）")
    rating: Optional[float] = Field(None, ge=0, le=5, description="评分")
    review_count: Optional[int] = Field(None, ge=0, description="评论数")
    image_url: Optional[str] = Field(None, description="主图 URL")
    product_url: Optional[str] = Field(None, description="商品页 URL")
    is_prime: bool = Field(default=False, description="是否 Prime 商品")
    brand: Optional[str] = Field(None, max_length=100, description="品牌")
    seller: Optional[str] = Field(None, max_length=200, description="卖家名")
    listing_date: Optional[str] = Field(None, description="首次上架日期（如 'January 1, 2024'）")
    category_path: Optional[str] = Field(None, description="类目路径")
    scraped_at: datetime = Field(default_factory=datetime.now, description="爬取时间")


class AlibabaProduct(BaseModel):
    """1688 商品模型"""

    item_id: str = Field(..., description="1688 商品 ID")
    title: str = Field(..., max_length=500, description="商品标题")
    price: float = Field(..., ge=0, description="单价（元）")
    min_order_qty: int = Field(default=1, gt=0, description="起订量")
    supplier: str = Field(default="Unknown", max_length=100, description="供应商/店铺名")
    supplier_rating: Optional[float] = Field(None, ge=0, le=5, description="供应商评分")
    location: Optional[str] = Field(None, description="发货地")
    image_url: Optional[str] = Field(None, description="主图 URL")
    item_url: Optional[str] = Field(None, description="商品页 URL")
    matched_score: float = Field(default=0.0, ge=0, le=100, description="匹配分数")
    scraped_at: datetime = Field(default_factory=datetime.now, description="爬取时间")

    @property
    def moq(self) -> int:
        """min_order_qty 的别名，保持向后兼容"""
        return self.min_order_qty


class MatchResult(BaseModel):
    """匹配结果模型"""

    amazon: AmazonProduct
    alibaba: AlibabaProduct
    score: float = Field(..., ge=0, le=100, description="综合匹配分数")
    price_diff_usd: float = Field(..., description="单价差额（美元）")
    estimated_profit_margin: float = Field(..., description="预估利润率 (%)")
    total_cost_usd: float = Field(..., description="总成本（含运费）")
    confidence: str = Field(..., description="置信度（high/medium/low）")
    recommendation: str = Field(..., description="推荐建议")
    matched_at: datetime = Field(default_factory=datetime.now, description="匹配时间")

    @property
    def confidence_level(self) -> str:
        """根据分数计算置信度"""
        if self.score >= 80:
            return "high"
        elif self.score >= 60:
            return "medium"
        return "low"
