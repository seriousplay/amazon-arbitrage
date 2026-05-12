"""
匹配评分引擎 — 综合评估 Amazon 商品与 1688 货源的套利价值
"""

from app.models.product import AlibabaProduct, AmazonProduct, MatchResult


class MatchScorer:
    """匹配评分引擎"""

    def __init__(self, config):
        self.config = config

    def _float_config(self, *names: str, default: float) -> float:
        for name in names:
            value = getattr(self.config, name, None)
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    pass
        return default

    @property
    def cny_rate(self) -> float:
        return self._float_config("CNY_TO_USD", "cny_to_usd", default=0.14)

    @property
    def cost_mul(self) -> float:
        return self._float_config("COST_MULTIPLIER", "cost_multiplier", default=1.25)

    def score_match(self, amazon: AmazonProduct, alibaba: AlibabaProduct) -> MatchResult:
        """计算单个 Amazon-1688 匹配对的套利评分。"""
        # 1688 价格转为美元并计算落地成本
        rate = self.cny_rate
        mul = self.cost_mul
        alibaba_cost_usd = alibaba.price * rate * mul
        amazon_price = amazon.price or 0
        price_diff = amazon_price - alibaba_cost_usd

        # 1. 价差评分（0-100）
        #    利润率 ≥ 100% → 满分；负利润 → 0 分
        if price_diff <= 0 or amazon_price <= 0:
            price_score = 0.0
        else:
            margin = (price_diff / amazon_price) * 100
            price_score = min(100.0, margin)

        # 2. 销量评分（0-100）
        #    基于评论数的对数映射：50000 评 → 100, 100 评 → 33
        review_count = amazon.review_count or 0
        if review_count >= 50000:
            sales_score = 100.0
        elif review_count >= 10000:
            sales_score = 80.0
        elif review_count >= 1000:
            sales_score = 55.0
        elif review_count >= 100:
            sales_score = 30.0
        elif review_count > 0:
            sales_score = 15.0
        else:
            sales_score = 5.0

        # 3. 商品评分（0-100）
        #    5.0 → 100, 4.0 → 80, 3.0 → 60
        rating = amazon.rating or 0.0
        rating_score = rating * 20.0

        # 4. 竞争评分（0-100，暂为固定及格分，后续接入卖家数/BSR）
        rank = amazon.rank or 0
        if rank <= 100:
            competition_score = 40.0  # 头部商品竞争激烈
        elif rank <= 1000:
            competition_score = 60.0
        elif rank <= 10000:
            competition_score = 80.0
        else:
            competition_score = 90.0  # 长尾竞争小

        # 加权总分（各维度已归一化到 0-100，加权后自然在 0-100）
        total = (
            price_score * self.config.PRICE_DIFF_WEIGHT
            + sales_score * self.config.SALES_WEIGHT
            + rating_score * self.config.RATING_WEIGHT
            + competition_score * self.config.COMPETITION_WEIGHT
        )
        score = min(100.0, max(0.0, round(total, 1)))

        # 利润率
        profit_margin = (price_diff / amazon_price) * 100 if amazon_price > 0 else 0.0
        total_cost = alibaba_cost_usd * alibaba.min_order_qty

        # 置信度
        if score >= 80:
            confidence = "high"
        elif score >= 60:
            confidence = "medium"
        else:
            confidence = "low"

        return MatchResult(
            amazon=amazon,
            alibaba=alibaba,
            score=score,
            price_diff_usd=round(price_diff, 2),
            estimated_profit_margin=round(profit_margin, 1),
            total_cost_usd=round(total_cost, 2),
            confidence=confidence,
            recommendation=self._get_recommendation(score, price_diff, alibaba.min_order_qty),
        )

    def _get_recommendation(self, score: float, price_diff: float, moq: int) -> str:
        if score >= 80 and price_diff > 0:
            return f"强烈推荐（MOQ: {moq}, 利润空间充足）"
        elif score >= 60 and price_diff > 0:
            return f"建议测试（MOQ: {moq}, 需核算成本）"
        elif price_diff <= 0:
            return "价差为负，不推荐"
        else:
            return "分数偏低，谨慎考虑"
