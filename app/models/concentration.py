"""
集中度分析数据模型 — 品牌集中度、价格区间、卖家集中度
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BrandShare:
    """单个品牌的市场份额"""
    brand: str
    product_count: int          # 该品牌在 Top N 中的产品数
    share_percent: float        # 市场份额（%）
    avg_price: float            # 该品牌平均售价
    avg_rating: float           # 该品牌平均评分
    avg_rank: float             # 该品牌平均 BSR 排名


@dataclass
class BrandConcentration:
    """品牌集中度分析结果"""
    brands: List[BrandShare]          # 按份额降序排列
    top_3_share: float                # CR3 — 前 3 品牌市场份额
    top_5_share: float                # CR5 — 前 5 品牌市场份额
    top_10_share: float               # CR10 — 前 10 品牌市场份额
    total_brands: int                 # 品牌总数
    unique_brands_in_top_10: int      # Top 10 中品牌数量
    hhi: float                        # Herfindahl-Hirschman 指数
    level: str                        # 高集中度 / 中集中度 / 低集中度


@dataclass
class PriceBucket:
    """价格区间桶"""
    label: str                        # 如 "$10-$15"
    min_price: float
    max_price: float
    product_count: int                # 该区间产品数
    share_percent: float              # 占比（%）
    brands: List[str]                 # 该区间的品牌列表
    avg_rating: float                 # 平均评分
    avg_reviews: float                # 平均评论数


@dataclass
class PriceRangeAnalysis:
    """价格区间分析结果"""
    buckets: List[PriceBucket]        # 所有价格桶（按价格升序）
    average_price: float              # 平均价格
    median_price: float               # 中位价格
    min_price: float                  # 最低价
    max_price: float                  # 最高价
    main_cluster_label: str           # 主要成交区间标签
    main_cluster_share: float         # 主要成交区间占比
    vacuum_zones: List[str]           # 真空区间描述
    recommended_entry: str            # 建议切入价位


@dataclass
class SellerShare:
    """单个卖家的市场份额"""
    seller: str
    product_count: int
    share_percent: float


@dataclass
class SellerConcentration:
    """卖家集中度分析结果"""
    sellers: List[SellerShare]
    top_3_share: float
    top_5_share: float
    total_sellers: int
    level: str


@dataclass
class ConcentrationResult:
    """综合集中度分析结果"""
    category: str
    total_products_analyzed: int      # 分析的产品总数
    brand_concentration: BrandConcentration
    seller_concentration: Optional[SellerConcentration] = None
    price_analysis: PriceRangeAnalysis = None
    product_diversity_note: str = ""  # 产品多样性结论
    overall_verdict: str = ""         # 综合判断：建议/谨慎/不推荐
    scraped_at: str = ""              # 分析时间

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "total_products_analyzed": self.total_products_analyzed,
            "brand_concentration": {
                "brands": [
                    {
                        "brand": b.brand,
                        "product_count": b.product_count,
                        "share_percent": round(b.share_percent, 1),
                        "avg_price": round(b.avg_price, 2),
                        "avg_rating": round(b.avg_rating, 2),
                        "avg_rank": round(b.avg_rank, 1),
                    }
                    for b in self.brand_concentration.brands
                ],
                "top_3_share": round(self.brand_concentration.top_3_share, 1),
                "top_5_share": round(self.brand_concentration.top_5_share, 1),
                "top_10_share": round(self.brand_concentration.top_10_share, 1),
                "total_brands": self.brand_concentration.total_brands,
                "unique_brands_in_top_10": self.brand_concentration.unique_brands_in_top_10,
                "hhi": round(self.brand_concentration.hhi, 1),
                "level": self.brand_concentration.level,
            },
            "seller_concentration": (
                {
                    "sellers": [
                        {"seller": s.seller, "product_count": s.product_count,
                         "share_percent": round(s.share_percent, 1)}
                        for s in self.seller_concentration.sellers
                    ],
                    "top_3_share": round(self.seller_concentration.top_3_share, 1),
                    "top_5_share": round(self.seller_concentration.top_5_share, 1),
                    "total_sellers": self.seller_concentration.total_sellers,
                    "level": self.seller_concentration.level,
                }
                if self.seller_concentration else None
            ),
            "price_analysis": (
                {
                    "buckets": [
                        {
                            "label": b.label,
                            "product_count": b.product_count,
                            "share_percent": round(b.share_percent, 1),
                            "brands": b.brands[:5],
                            "avg_rating": round(b.avg_rating, 2),
                            "avg_reviews": round(b.avg_reviews, 1),
                        }
                        for b in self.price_analysis.buckets
                    ],
                    "average_price": round(self.price_analysis.average_price, 2),
                    "median_price": round(self.price_analysis.median_price, 2),
                    "min_price": round(self.price_analysis.min_price, 2),
                    "max_price": round(self.price_analysis.max_price, 2),
                    "main_cluster": self.price_analysis.main_cluster_label,
                    "main_cluster_share": round(self.price_analysis.main_cluster_share, 1),
                    "vacuum_zones": self.price_analysis.vacuum_zones,
                    "recommended_entry": self.price_analysis.recommended_entry,
                }
                if self.price_analysis else None
            ),
            "product_diversity_note": self.product_diversity_note,
            "overall_verdict": self.overall_verdict,
            "scraped_at": self.scraped_at,
        }
