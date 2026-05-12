"""
市场集中度分析引擎 — 品牌集中度 / 价格区间 / 卖家集中度
对应选品逻辑第 3 条（集中度）和第 5 条（价格区间）
"""

import statistics
from collections import Counter
from typing import Dict, List, Optional, Tuple

from app.models.concentration import (
    BrandConcentration,
    BrandShare,
    ConcentrationResult,
    PriceBucket,
    PriceRangeAnalysis,
    SellerConcentration,
    SellerShare,
)
from app.models.product import AmazonProduct
from app.utils.logger import get_logger

logger = get_logger(__name__)


class MarketConcentrationAnalyzer:
    """市场集中度分析器"""

    # HHI 阈值（针对 Top 100 市场）
    HHI_HIGH = 2500  # ≥2500 → 高集中度（寡占）
    HHI_MODERATE = 1500  # 1500-2500 → 中集中度
    # CR3 阈值（辅助判断）
    CR3_HIGH = 60  # ≥60% → 高集中度
    CR3_LOW = 30  # ≤30% → 低集中度

    # 价格区间粒度（按不同价格段自适应）
    PRICE_BUCKET_SIZE = {
        (0, 10): 2,  # $0-10: 每 $2 一个区间
        (10, 25): 5,  # $10-25: 每 $5
        (25, 50): 10,  # $25-50: 每 $10
        (50, 100): 20,  # $50-100: 每 $20
        (100, 500): 50,  # $100+: 每 $50
    }

    def __init__(self):
        self._products: List[AmazonProduct] = []
        self._brand_counts: Counter = Counter()
        self._prices: List[float] = []

    # ─── 主入口 ──────────────────────────────────────────

    def analyze(
        self,
        products: List[AmazonProduct],
        category: str,
    ) -> ConcentrationResult:
        """对一批 Amazon 商品执行完整的集中度分析"""
        if not products:
            logger.warning("集中度分析：产品列表为空")
            return self._empty_result(category)

        self._products = products
        self._brand_counts = Counter(p.brand or "未知品牌" for p in products)
        self._prices = [p.price for p in products if p.price is not None and p.price > 0]

        logger.info(
            f"集中度分析: 类别={category}, "
            f"产品={len(products)}, "
            f"有价格={len(self._prices)}, "
            f"品牌数={len(self._brand_counts)}"
        )

        # 品牌集中度
        brand_conc = self._analyze_brand_concentration()

        # 卖家集中度
        seller_conc = self._analyze_seller_concentration()

        # 价格区间
        price_analysis = self._analyze_price_ranges()

        # 综合判断
        diversity_note = self._product_diversity_note(brand_conc)
        verdict = self._overall_verdict(brand_conc, price_analysis)

        result = ConcentrationResult(
            category=category,
            total_products_analyzed=len(products),
            brand_concentration=brand_conc,
            seller_concentration=seller_conc,
            price_analysis=price_analysis,
            product_diversity_note=diversity_note,
            overall_verdict=verdict,
            scraped_at=(
                products[0].scraped_at.isoformat() if hasattr(products[0], "scraped_at") else ""
            ),
        )

        logger.info(f"集中度分析完成: {verdict}")
        return result

    # ─── 品牌集中度 ──────────────────────────────────────

    def _analyze_brand_concentration(self) -> BrandConcentration:
        """分析品牌集中度（CR3 / CR5 / CR10 / HHI）"""
        if not self._brand_counts:
            return BrandConcentration(
                brands=[],
                top_3_share=0,
                top_5_share=0,
                top_10_share=0,
                total_brands=0,
                unique_brands_in_top_10=0,
                hhi=0,
                level="数据不足",
            )

        total = sum(self._brand_counts.values())
        # 按出现次数降序
        sorted_brands = self._brand_counts.most_common()

        brand_shares = []
        for brand, count in sorted_brands:
            products_of_brand = [p for p in self._products if (p.brand or "未知品牌") == brand]
            avg_price = (
                statistics.mean([p.price for p in products_of_brand if p.price])
                if any(p.price for p in products_of_brand)
                else 0
            )
            avg_rating = (
                statistics.mean([p.rating for p in products_of_brand if p.rating])
                if any(p.rating for p in products_of_brand)
                else 0
            )
            avg_rank = (
                statistics.mean([p.rank for p in products_of_brand if p.rank])
                if any(p.rank for p in products_of_brand)
                else 0
            )

            brand_shares.append(
                BrandShare(
                    brand=brand,
                    product_count=count,
                    share_percent=(count / total) * 100,
                    avg_price=avg_price,
                    avg_rating=avg_rating,
                    avg_rank=avg_rank,
                )
            )

        # 计算 CR3 / CR5 / CR10
        cum_share = 0
        top_3_share = top_5_share = top_10_share = 0.0
        for i, bs in enumerate(brand_shares):
            cum_share += bs.share_percent
            if i == 2:
                top_3_share = cum_share
            if i == 4:
                top_5_share = cum_share
            if i == 9:
                top_10_share = cum_share
        # 如果品牌数不足阈值，用累计值
        if len(brand_shares) < 3:
            top_3_share = cum_share
        if len(brand_shares) < 5:
            top_5_share = cum_share
        if len(brand_shares) < 10:
            top_10_share = cum_share

        # HHI = Σ(市场份额百分比²)，标准 HHI 范围 0-10000
        # 例如 40% → 1600, 25% → 625, 合计 2750 → 中高集中度
        hhi = sum(bs.share_percent**2 for bs in brand_shares)

        # 等级判断
        level = self._brand_level(top_3_share, hhi)

        # Top 10 产品中的品牌数（产品多样性）
        top_10_products = self._products[:10]
        unique_brands_top10 = len(set(p.brand for p in top_10_products if p.brand))

        return BrandConcentration(
            brands=brand_shares,
            top_3_share=round(top_3_share, 1),
            top_5_share=round(top_5_share, 1),
            top_10_share=round(top_10_share, 1),
            total_brands=len(brand_shares),
            unique_brands_in_top_10=unique_brands_top10,
            hhi=round(hhi, 1),
            level=level,
        )

    def _brand_level(self, cr3: float, hhi: float) -> str:
        """判断品牌集中度等级"""
        # HHI 优先
        if hhi >= self.HHI_HIGH:
            return "高集中度"
        elif hhi >= self.HHI_MODERATE:
            return "中集中度"

        # HHI 不足时用 CR3 辅助
        if cr3 >= self.CR3_HIGH:
            return "高集中度"
        elif cr3 >= self.CR3_LOW:
            return "中集中度"
        else:
            return "低集中度"

    # ─── 卖家集中度 ──────────────────────────────────────

    def _analyze_seller_concentration(self) -> Optional[SellerConcentration]:
        """
        卖家集中度分析。
        注意：当前 AmazonProduct 模型不含 seller 字段，
        若数据中存在 seller 属性则分析，否则返回 None。
        """
        sellers = []
        for p in self._products:
            seller = getattr(p, "seller", None) or getattr(p, "seller_name", None)
            if seller:
                sellers.append(seller)

        if not sellers:
            return None  # 暂无法采集卖家数据

        seller_counts = Counter(sellers)
        total = len(sellers)
        sorted_sellers = seller_counts.most_common()

        seller_shares = [
            SellerShare(
                seller=s,
                product_count=c,
                share_percent=(c / total) * 100,
            )
            for s, c in sorted_sellers
        ]

        cum = 0
        top_3 = top_5 = 0.0
        for i, ss in enumerate(seller_shares):
            cum += ss.share_percent
            if i == 2:
                top_3 = cum
            if i == 4:
                top_5 = cum
        if len(seller_shares) < 3:
            top_3 = cum
        if len(seller_shares) < 5:
            top_5 = cum

        level = "高集中度" if top_3 >= 60 else "中集中度" if top_3 >= 30 else "低集中度"

        return SellerConcentration(
            sellers=seller_shares,
            top_3_share=round(top_3, 1),
            top_5_share=round(top_5, 1),
            total_sellers=len(seller_shares),
            level=level,
        )

    # ─── 价格区间分析 ────────────────────────────────────

    def _analyze_price_ranges(self) -> PriceRangeAnalysis:
        """分析价格区间分布，识别主力区间和真空区间"""
        if not self._prices:
            return PriceRangeAnalysis(
                buckets=[],
                average_price=0,
                median_price=0,
                min_price=0,
                max_price=0,
                main_cluster_label="",
                main_cluster_share=0,
                vacuum_zones=["数据不足"],
                recommended_entry="",
            )

        prices_sorted = sorted(self._prices)
        avg_price = statistics.mean(prices_sorted)
        median_price = statistics.median(prices_sorted)
        min_price = prices_sorted[0]
        max_price = prices_sorted[-1]

        # 自适应区间划分
        buckets = self._build_price_buckets(prices_sorted)

        # 找出主力区间（产品最多的区间）
        main_bucket = max(buckets, key=lambda b: b.product_count)
        main_cluster_share = main_bucket.share_percent

        # 识别真空区间（相邻高密度区间之间的价格带）
        vacuum_zones = self._identify_vacuum_zones(buckets)

        # 建议切入价位
        recommended_entry = self._recommend_entry(buckets, avg_price, median_price, vacuum_zones)

        return PriceRangeAnalysis(
            buckets=buckets,
            average_price=avg_price,
            median_price=median_price,
            min_price=min_price,
            max_price=max_price,
            main_cluster_label=main_bucket.label,
            main_cluster_share=main_cluster_share,
            vacuum_zones=vacuum_zones,
            recommended_entry=recommended_entry,
        )

    def _get_bucket_size(self, price: float) -> float:
        """根据价格返回合适的区间粒度"""
        for (lo, hi), size in self.PRICE_BUCKET_SIZE.items():
            if lo <= price < hi:
                return size
        return 50  # $500+ 每 $50

    def _build_price_buckets(self, prices: List[float]) -> List[PriceBucket]:
        """构建自适应价格区间桶"""
        if not prices:
            return []

        max_price = max(prices)
        bucket_size = self._get_bucket_size(max_price)

        # 按区间聚合
        buckets_map: Dict[str, dict] = {}
        for p in prices:
            lo = (p // bucket_size) * bucket_size
            hi = lo + bucket_size
            label = f"${lo:.0f}-${hi:.0f}"
            if label not in buckets_map:
                buckets_map[label] = {
                    "min": lo,
                    "max": hi,
                    "products": [],
                    "brands": set(),
                    "ratings": [],
                    "reviews": [],
                }
            buckets_map[label]["products"].append(p)
            buckets_map[label]["brands"].add(self._get_brand_for_price(p))
            r = self._get_rating_for_price(p)
            if r:
                buckets_map[label]["ratings"].append(r)
            rv = self._get_reviews_for_price(p)
            if rv:
                buckets_map[label]["reviews"].append(rv)

        total = len(prices)
        buckets = []
        for label in sorted(buckets_map.keys(), key=lambda x: float(x.split("-")[0].strip("$"))):
            data = buckets_map[label]
            count = len(data["products"])
            avg_rat = statistics.mean(data["ratings"]) if data["ratings"] else 0
            avg_rev = statistics.mean(data["reviews"]) if data["reviews"] else 0
            buckets.append(
                PriceBucket(
                    label=label,
                    min_price=data["min"],
                    max_price=data["max"],
                    product_count=count,
                    share_percent=(count / total) * 100,
                    brands=sorted(data["brands"])[:10],
                    avg_rating=avg_rat,
                    avg_reviews=avg_rev,
                )
            )

        return buckets

    def _identify_vacuum_zones(self, buckets: List[PriceBucket]) -> List[str]:
        """识别价格真空区间（产品很少的价格带）"""
        vacuum_zones = []
        for i, bucket in enumerate(buckets):
            # 产品数少于总产品数的 5% 且前后区间产品数都多于它
            if bucket.product_count <= max(1, len(self._prices) * 0.05):
                # 检查是否是孤立的（周围区间产品更多）
                left_dense = i > 0 and buckets[i - 1].product_count > bucket.product_count * 2
                right_dense = (
                    i < len(buckets) - 1 and buckets[i + 1].product_count > bucket.product_count * 2
                )
                if left_dense or right_dense:
                    vacuum_zones.append(
                        f"{bucket.label}: 仅 {bucket.product_count} 个产品 "
                        f"({bucket.share_percent:.0f}%)，"
                        f"周围区间密度较高"
                    )

        return vacuum_zones[:5]  # 最多显示 5 个

    def _recommend_entry(
        self,
        buckets: List[PriceBucket],
        avg_price: float,
        median_price: float,
        vacuum_zones: List[str],
    ) -> str:
        """建议切入价位"""
        if vacuum_zones:
            # 有真空区间 → 建议切入
            zone = vacuum_zones[0]
            price_range = zone.split(":")[0]
            return f"建议切入 {price_range} 真空区间，避开主力竞争带"

        # 无真空区间 → 看中位价附近
        mid_bucket = None
        for b in buckets:
            if b.min_price <= median_price <= b.max_price:
                mid_bucket = b
                break

        if mid_bucket and mid_bucket.share_percent >= 30:
            return (
                f"主力成交区间 {mid_bucket.label}"
                f"（占 {mid_bucket.share_percent:.0f}%），"
                f"建议在 ±20% 价格带内做差异化"
            )
        else:
            return f"价格分布较分散，建议参考中位价 ${median_price:.2f} 附近切入"

    def _get_brand_for_price(self, price: float) -> str:
        """辅助：根据价格查找对应品牌（用于价格桶）"""
        for p in self._products:
            if p.price and abs(p.price - price) < 0.01:
                return p.brand or "未知品牌"
        return "未知品牌"

    def _get_rating_for_price(self, price: float) -> Optional[float]:
        for p in self._products:
            if p.price and abs(p.price - price) < 0.01:
                return p.rating
        return None

    def _get_reviews_for_price(self, price: float) -> Optional[int]:
        for p in self._products:
            if p.price and abs(p.price - price) < 0.01:
                return p.review_count
        return None

    # ─── 综合判断 ────────────────────────────────────────

    def _product_diversity_note(self, brand_conc: BrandConcentration) -> str:
        """产品多样性结论"""
        if brand_conc.top_3_share >= 80:
            return (
                f"头部 {brand_conc.total_brands} 个品牌占据了 "
                f"{brand_conc.top_3_share:.0f}% 的 Top 100 份额，"
                f"品牌垄断严重，新品突围难度较大。"
            )
        elif brand_conc.top_3_share >= 50:
            return (
                f"Top 3 品牌占 {brand_conc.top_3_share:.0f}%，"
                f"品牌集中度中等，"
                f"仍有差异化切入空间。"
            )
        else:
            return (
                f"品牌较分散（Top 3 仅 {brand_conc.top_3_share:.0f}%），"
                f"类目竞争以产品力驱动为主，新品机会较好。"
            )

    def _overall_verdict(
        self,
        brand_conc: BrandConcentration,
        price_analysis: PriceRangeAnalysis,
    ) -> str:
        """综合判断是否建议进入该类目"""
        reasons = []

        # 品牌集中度
        if brand_conc.level == "高集中度":
            reasons.append("品牌集中度高")
        elif brand_conc.level == "低集中度":
            reasons.append("品牌壁垒低")

        # 价格区间
        if price_analysis and price_analysis.vacuum_zones:
            reasons.append(f"存在价格真空区间({len(price_analysis.vacuum_zones)}个)")

        if not reasons:
            return "综合判断：类目结构健康"

        if brand_conc.level == "高集中度" and not price_analysis.vacuum_zones:
            return "综合判断：⚠️ 谨慎进入 — 品牌垄断且无价格真空区"

        return "综合判断：✅ 有切入点 — " + "，".join(reasons)

    def _empty_result(self, category: str) -> ConcentrationResult:
        return ConcentrationResult(
            category=category,
            total_products_analyzed=0,
            brand_concentration=BrandConcentration(
                brands=[],
                top_3_share=0,
                top_5_share=0,
                top_10_share=0,
                total_brands=0,
                unique_brands_in_top_10=0,
                hhi=0,
                level="数据不足",
            ),
            overall_verdict="无数据",
        )

    # ─── 批量接口 ────────────────────────────────────────

    def analyze_batch(
        self,
        category_results: Dict[str, List[AmazonProduct]],
    ) -> Dict[str, ConcentrationResult]:
        """批量分析多个品类的集中度（用于跨类目对比）"""
        return {cat: self.analyze(products, cat) for cat, products in category_results.items()}
