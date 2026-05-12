"""
新品渗透分析引擎 — 上架时间 / 新品率 / 新品表现对比
对应选品逻辑第 7 条（新品占有率）
"""

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.models.product import AmazonProduct
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ─── 日期解析器 ──────────────────────────────────────────

MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
    # 中文月份
    "1月": 1,
    "2月": 2,
    "3月": 3,
    "4月": 4,
    "5月": 5,
    "6月": 6,
    "7月": 7,
    "8月": 8,
    "9月": 9,
    "10月": 10,
    "11月": 11,
    "12月": 12,
}


def parse_listing_date(date_str: Optional[str]) -> Optional[datetime]:
    """解析 Amazon 上架日期字符串，支持多种格式"""
    if not date_str or not date_str.strip():
        return None

    text = date_str.strip()

    # 格式 1: "January 1, 2024" / "Jan 1, 2024"
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2})[,，]?\s*(\d{4})", text)
    if m:
        month_name = m.group(1).lower()
        day = int(m.group(2))
        year = int(m.group(3))
        month = MONTH_NAMES.get(month_name)
        if month:
            try:
                return datetime(year, month, day, tzinfo=timezone.utc)
            except ValueError:
                return None

    # 格式 2: "2024-01-01" 或 "2024/01/01"
    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        try:
            return datetime(
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                tzinfo=timezone.utc,
            )
        except ValueError:
            return None

    # 格式 3: 中文 "2024年1月1日"
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if m:
        try:
            return datetime(
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                tzinfo=timezone.utc,
            )
        except ValueError:
            return None

    # 格式 4: 仅年份 "2024"
    m = re.match(r"(\d{4})", text)
    if m:
        year = int(m.group(1))
        if 2010 <= year <= 2030:
            return datetime(year, 7, 1, tzinfo=timezone.utc)  # 默认年中

    # 格式 5: 相对时间格式（Amazon 偶尔用）
    # 如 "30 days ago"、"3 months ago" — 在 BSR 页不常见
    m = re.match(r"(\d+)\s+(day|month|year)s?\s+ago", text, re.IGNORECASE)
    if m:
        num = int(m.group(1))
        unit = m.group(2).lower()
        now = datetime.now(timezone.utc)
        if unit == "day":
            return now.replace(day=max(1, now.day - num))
        elif unit == "month":
            month = now.month - num
            year = now.year
            while month <= 0:
                month += 12
                year -= 1
            return datetime(year, month, 1, tzinfo=timezone.utc)
        elif unit == "year":
            return datetime(now.year - num, 1, 1, tzinfo=timezone.utc)

    return None


def months_since(date: Optional[datetime]) -> Optional[float]:
    """计算从给定日期到现在的月数"""
    if not date:
        return None
    now = datetime.now(timezone.utc)
    return round((now - date).days / 30.44, 1)


# ─── 分析结果模型 ────────────────────────────────────────

from dataclasses import dataclass
from typing import List as ListType


@dataclass
class NewProductAnalysis:
    """新品渗透分析结果"""

    # 基本信息
    total_products: int  # 总分析产品数
    with_listing_date: int  # 有上架日期数据的产品数
    listing_date_coverage: float  # 日期数据覆盖率（%）

    # 新品率
    new_product_count: int  # 上架 ≤12 个月的产品数
    new_product_share: float  # 新品占比（%）

    # 新品 vs 老品对比
    new_avg_rating: float  # 新品平均评分
    old_avg_rating: float  # 老品平均评分
    new_avg_reviews: float  # 新品平均评论数
    old_avg_reviews: float  # 老品平均评论数
    new_avg_price: float  # 新品平均售价
    old_avg_price: float  # 老品平均售价
    new_avg_rank: float  # 新品平均 BSR 排名
    old_avg_rank: float  # 老品平均 BSR 排名

    # 时间分布
    avg_listing_age_months: float  # 平均在架月数
    oldest_listing_date: Optional[str]  # 最早上架日期
    newest_listing_date: Optional[str]  # 最近上架日期

    # Top 10 分析
    top_10_new_count: int  # Top 10 中有几个新品
    top_10_new_share: float  # Top 10 新品占比（%）

    # 新品机会判断
    new_product_opportunity: str  # 高 / 中 / 低
    opportunity_reason: str  # 判断理由

    def to_dict(self) -> dict:
        return {
            "total_products": self.total_products,
            "with_listing_date": self.with_listing_date,
            "listing_date_coverage": round(self.listing_date_coverage, 1),
            "new_product_rate": {
                "new_count": self.new_product_count,
                "new_share_percent": round(self.new_product_share, 1),
                "established_count": self.total_products - self.new_product_count,
            },
            "new_vs_established": {
                "new_avg_rating": round(self.new_avg_rating, 2),
                "old_avg_rating": round(self.old_avg_rating, 2),
                "new_avg_reviews": round(self.new_avg_reviews, 1),
                "old_avg_reviews": round(self.old_avg_reviews, 1),
                "new_avg_price": round(self.new_avg_price, 2),
                "old_avg_price": round(self.old_avg_price, 2),
                "new_avg_rank": round(self.new_avg_rank, 1),
                "old_avg_rank": round(self.old_avg_rank, 1),
            },
            "timing": {
                "avg_listing_age_months": round(self.avg_listing_age_months, 1),
                "oldest_listing_date": self.oldest_listing_date or "unknown",
                "newest_listing_date": self.newest_listing_date or "unknown",
            },
            "top_10_new_share": {
                "new_in_top_10": self.top_10_new_count,
                "share_percent": round(self.top_10_new_share, 1),
            },
            "opportunity": {
                "level": self.new_product_opportunity,
                "reason": self.opportunity_reason,
            },
        }


# ─── 分析引擎 ────────────────────────────────────────────


class NewProductAnalyzer:
    """新品渗透分析器"""

    NEW_PRODUCT_MONTHS = 12  # ≤12 个月算新品
    HIGH_OPPORTUNITY_MIN = 20  # 新品率 ≥20% → 机会高
    LOW_OPPORTUNITY_MAX = 5  # 新品率 ≤5% → 机会低

    def analyze(self, products: ListType[AmazonProduct]) -> NewProductAnalysis:
        """对一批 Amazon 商品执行新品渗透分析"""
        n = len(products)
        if n == 0:
            return self._empty_result()

        # 解析上架日期
        dated_products: List[Tuple[AmazonProduct, datetime, float]] = []
        no_date_count = 0
        for p in products:
            dt = parse_listing_date(p.listing_date)
            if dt:
                age = months_since(dt)
                if age is not None:
                    dated_products.append((p, dt, age))
            else:
                no_date_count += 1

        if not dated_products:
            logger.warning("新品分析：无产品有上架日期数据")
            return self._empty_result()

        with_date = len(dated_products)
        coverage = (with_date / n) * 100

        # 分类新品/老品
        new_products = [
            (p, dt, age) for p, dt, age in dated_products if age <= self.NEW_PRODUCT_MONTHS
        ]
        old_products = [
            (p, dt, age) for p, dt, age in dated_products if age > self.NEW_PRODUCT_MONTHS
        ]

        new_count = len(new_products)
        new_share = (new_count / with_date) * 100

        # 统计指标
        def avg(plist: List, attr: str) -> float:
            vals = [getattr(p, attr) for p, _, _ in plist if getattr(p, attr) is not None]
            return sum(vals) / len(vals) if vals else 0.0

        new_avg_rating = avg(new_products, "rating") if new_products else 0.0
        old_avg_rating = avg(old_products, "rating") if old_products else 0.0
        new_avg_reviews = avg(new_products, "review_count") if new_products else 0.0
        old_avg_reviews = avg(old_products, "review_count") if old_products else 0.0
        new_avg_price = avg(new_products, "price") if new_products else 0.0
        old_avg_price = avg(old_products, "price") if old_products else 0.0
        new_avg_rank = avg(new_products, "rank") if new_products else 0.0
        old_avg_rank = avg(old_products, "rank") if old_products else 0.0

        # 所有产品平均在架月数
        all_ages = [age for _, _, age in dated_products]
        avg_age = sum(all_ages) / len(all_ages)

        # 最早/最近上架
        sorted_by_date = sorted(dated_products, key=lambda x: x[1])
        oldest = sorted_by_date[0][0].listing_date if sorted_by_date else None
        newest = sorted_by_date[-1][0].listing_date if sorted_by_date else None

        # Top 10 新品占比
        top_10 = products[:10]
        top_10_new = sum(
            1
            for p in top_10
            if p.listing_date
            and parse_listing_date(p.listing_date)
            and months_since(parse_listing_date(p.listing_date)) is not None
            and months_since(parse_listing_date(p.listing_date)) <= self.NEW_PRODUCT_MONTHS
        )
        top_10_new_share = (top_10_new / len(top_10)) * 100 if top_10 else 0

        # 新品机会判断
        opportunity, reason = self._assess_opportunity(
            new_share,
            new_avg_reviews,
            old_avg_reviews,
            new_avg_rating,
            old_avg_rating,
            top_10_new_share,
        )

        return NewProductAnalysis(
            total_products=n,
            with_listing_date=with_date,
            listing_date_coverage=coverage,
            new_product_count=new_count,
            new_product_share=new_share,
            new_avg_rating=new_avg_rating,
            old_avg_rating=old_avg_rating,
            new_avg_reviews=new_avg_reviews,
            old_avg_reviews=old_avg_reviews,
            new_avg_price=new_avg_price,
            old_avg_price=old_avg_price,
            new_avg_rank=new_avg_rank,
            old_avg_rank=old_avg_rank,
            avg_listing_age_months=avg_age,
            oldest_listing_date=oldest,
            newest_listing_date=newest,
            top_10_new_count=top_10_new,
            top_10_new_share=top_10_new_share,
            new_product_opportunity=opportunity,
            opportunity_reason=reason,
        )

    def _assess_opportunity(
        self,
        new_share: float,
        new_reviews: float,
        old_reviews: float,
        new_rating: float,
        old_rating: float,
        top10_new_share: float,
    ) -> Tuple[str, str]:
        """评估新品进入机会"""
        reasons = []

        # 新品率
        if new_share >= self.HIGH_OPPORTUNITY_MIN:
            reasons.append(f"新品率高({new_share:.0f}%)")
        elif new_share <= self.LOW_OPPORTUNITY_MAX:
            reasons.append(f"新品率低({new_share:.0f}%)，老品主导")

        # 新品与老品的评论数差距（越小越容易追赶）
        if old_reviews > 0:
            review_gap_ratio = new_reviews / old_reviews if old_reviews > 0 else 0
            if review_gap_ratio >= 0.3:
                reasons.append("新品评论积累快，追赶老品容易")
            elif review_gap_ratio < 0.1:
                reasons.append("新品与老品评论数差距大")

        # Top 10 新品占比
        if top10_new_share >= 30:
            reasons.append("头部活跃，新品有上榜机会")
        elif top10_new_share == 0:
            reasons.append("Top 10 无新品，头部固化")

        # 综合判断
        if new_share >= self.HIGH_OPPORTUNITY_MIN:
            return "高", "；".join(reasons) if reasons else "新品活跃，进入机会好"
        elif new_share >= 10:
            return "中", "；".join(reasons) if reasons else "新品有一定空间"
        elif new_share >= self.LOW_OPPORTUNITY_MAX:
            return "低", "；".join(reasons) if reasons else "新品占比偏低，进入需谨慎"
        else:
            return "低", "；".join(reasons) if reasons else "几乎没有新品，类目壁垒高"

    def _empty_result(self) -> NewProductAnalysis:
        return NewProductAnalysis(
            total_products=0,
            with_listing_date=0,
            listing_date_coverage=0,
            new_product_count=0,
            new_product_share=0,
            new_avg_rating=0,
            old_avg_rating=0,
            new_avg_reviews=0,
            old_avg_reviews=0,
            new_avg_price=0,
            old_avg_price=0,
            new_avg_rank=0,
            old_avg_rank=0,
            avg_listing_age_months=0,
            oldest_listing_date=None,
            newest_listing_date=None,
            top_10_new_count=0,
            top_10_new_share=0,
            new_product_opportunity="数据不足",
            opportunity_reason="无法获取上架日期数据",
        )
