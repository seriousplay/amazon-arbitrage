"""
爆款选品智能评分引擎 — 基于 11 维度选品逻辑
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.models.product import AmazonProduct, MatchResult
from app.core.risk_assessor import RiskAssessor
from app.core.trends import TrendEngine


@dataclass
class BreakoutScore:
    """11 维度爆款评分"""

    # ─── 产品基本面（0-20分）─────────────────
    product_fundamentals: float = 0.0  # 产品质量/退货/复购预估
    # ─── 市场需求（0-20分）───────────────────
    market_demand: float = 0.0  # 销量/搜索量/趋势
    # ─── 竞争格局（0-15分）───────────────────
    competition: float = 0.0  # 集中度/新品机会
    # ─── 利润空间（0-20分）───────────────────
    profit_potential: float = 0.0  # 价差/利润率
    # ─── 供应链（0-10分）───────────────────
    supply_chain: float = 0.0  # 1688供给/物流
    # ─── 风险（0-10分，扣分制）──────────────
    risk: float = 0.0  # 侵权/季节/认证
    # ─── 趋势（0-5分）─────────────────────
    trend: float = 0.0  # 热搜/社媒热度

    @property
    def total(self) -> float:
        return min(
            100.0,
            sum(
                [
                    self.product_fundamentals,
                    self.market_demand,
                    self.competition,
                    self.profit_potential,
                    self.supply_chain,
                    self.risk,  # 风险已是负分
                    self.trend,
                ]
            ),
        )

    @property
    def grade(self) -> str:
        if self.total >= 80:
            return "S级爆款"
        elif self.total >= 65:
            return "A级潜力"
        elif self.total >= 50:
            return "B级观察"
        else:
            return "C级待定"

    def to_dict(self) -> dict:
        return {
            "total": round(self.total, 1),
            "grade": self.grade,
            "dimensions": {
                "product_fundamentals": round(self.product_fundamentals, 1),
                "market_demand": round(self.market_demand, 1),
                "competition": round(self.competition, 1),
                "profit_potential": round(self.profit_potential, 1),
                "supply_chain": round(self.supply_chain, 1),
                "risk": round(self.risk, 1),
                "trend": round(self.trend, 1),
            },
        }


class BreakoutScorer:
    """爆款评分器 — 综合Amazon数据+1688匹配+市场信号"""

    def __init__(self, config):
        self.config = config
        self.risk = RiskAssessor()
        self.trends = TrendEngine()

    def score(
        self,
        product: AmazonProduct,
        match: Optional[MatchResult] = None,
        market_data: Optional[dict] = None,
    ) -> BreakoutScore:
        """对单个商品进行11维评分"""
        s = BreakoutScore()

        # 1. 产品基本面（0-20）：评分+评论=需求验证
        rating = product.rating or 0
        reviews = product.review_count or 0
        if rating >= 4.5:
            s.product_fundamentals += 10
        elif rating >= 4.0:
            s.product_fundamentals += 7
        elif rating >= 3.5:
            s.product_fundamentals += 4
        if reviews >= 10000:
            s.product_fundamentals += 10
        elif reviews >= 1000:
            s.product_fundamentals += 7
        elif reviews >= 100:
            s.product_fundamentals += 4
        elif reviews >= 30:
            s.product_fundamentals += 2

        # 2. 市场需求（0-20）：BSR排名+评论增长率
        rank = product.rank or 0
        if rank <= 100:
            s.market_demand += 12
        elif rank <= 1000:
            s.market_demand += 9
        elif rank <= 5000:
            s.market_demand += 6
        elif rank <= 20000:
            s.market_demand += 3
        if reviews >= 500:
            s.market_demand += 8
        elif reviews >= 100:
            s.market_demand += 5

        # 3. 竞争格局（0-15）：基于BSR排名的竞争推断
        if rank <= 500:
            s.competition += 3  # 头部竞争激烈
        elif rank <= 5000:
            s.competition += 8  # 有机会
        else:
            s.competition += 10  # 长尾蓝海
        if reviews < 500:
            s.competition += 5  # 评论少=新品机会大

        # 4. 利润空间（0-20）：基于1688匹配
        if match:
            margin = match.estimated_profit_margin
            if margin >= 50:
                s.profit_potential += 15
            elif margin >= 30:
                s.profit_potential += 10
            elif margin >= 15:
                s.profit_potential += 5
            profit = match.price_diff_usd
            if profit >= 15:
                s.profit_potential += 5
            elif profit >= 5:
                s.profit_potential += 3

        # 5. 供应链（0-10）：基于1688匹配数量
        if match:
            s.supply_chain += 5  # 已匹配到货源
            alibaba_price = match.alibaba.price
            if alibaba_price <= 10:
                s.supply_chain += 3  # 低成本
            elif alibaba_price <= 30:
                s.supply_chain += 2
            if match.alibaba.min_order_qty <= 50:
                s.supply_chain += 2  # 低起订量

        # 6. 风险（0-10）：真实风险评估
        risk_data = self.risk.assess(product)
        s.risk = risk_data["score"]

        # 7. 趋势（0-5）：基于品类搜索热度
        trend_data = self.trends.get_trend(product.category_path or "", product.title)
        s.trend = trend_data["trend_score"]

        return s

    def score_batch(
        self,
        products: List[AmazonProduct],
        matches: Dict[str, MatchResult],
        market_data: Optional[dict] = None,
    ) -> List[dict]:
        """批量评分，返回按总分降序排列"""
        results = []
        for p in products:
            match = matches.get(p.asin)
            score = self.score(p, match, market_data)
            risk_data = self.risk.assess(p)
            trend_data = self.trends.get_trend(p.category_path or "", p.title)
            results.append(
                {
                    "asin": p.asin,
                    "title": p.title,
                    "rank": p.rank,
                    "price": p.price,
                    "rating": p.rating,
                    "review_count": p.review_count,
                    "brand": p.brand,
                    "category_path": p.category_path,
                    "breakout_score": score.to_dict(),
                    "risk_assessment": risk_data,
                    "trend_data": trend_data,
                    "has_match": match is not None,
                    "match_score": match.score if match else None,
                    "profit_margin": match.estimated_profit_margin if match else None,
                    "recommendation": score.grade,
                }
            )
        results.sort(key=lambda x: x["breakout_score"]["total"], reverse=True)
        return results
