"""
选品规则引擎 — 加载/验证/应用自定义筛选规则
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

from app.models.product import AmazonProduct, MatchResult

RULES_FILE = Path(__file__).parent.parent.parent / "data" / "categories.json"
PRESETS_FILE = Path(__file__).parent.parent.parent / "data" / "rule_presets.json"


@dataclass
class RulesConfig:
    """选品规则配置"""

    # ─── Amazon 发现阶段过滤 ──────────────
    min_price: float = 5.0  # 最低售价 ($)
    max_price: float = 200.0  # 最高售价 ($)
    min_rating: float = 3.5  # 最低评分
    min_reviews: int = 30  # 最低评论数
    max_bsr_rank: int = 50000  # BSR 排名上限（越小越头部）

    # ─── 1688 匹配阶段过滤 ───────────────
    min_price_ratio: float = 2.0  # Amazon / 1688落地成本 最低倍数（≥2倍价差）
    min_profit_usd: float = 3.0  # 最低单品利润 ($)
    min_profit_margin: float = 30.0  # 最低利润率 (%)

    # ─── 综合评分权重 ────────────────────
    price_diff_weight: float = 0.4
    sales_weight: float = 0.3
    rating_weight: float = 0.2
    competition_weight: float = 0.1
    min_score: float = 60.0  # 最低推荐分

    # ─── 其他 ────────────────────────────
    max_products_per_scan: int = 30
    require_prime: bool = False

    # 汇率和成本系数
    cny_to_usd: float = 0.14
    cost_multiplier: float = 1.25

    @classmethod
    def load(cls) -> "RulesConfig":
        """从 categories.json 加载规则"""
        if RULES_FILE.exists():
            try:
                data = json.loads(RULES_FILE.read_text())
                rules_data = data.get("rules", {})
                return cls(**{k: v for k, v in rules_data.items() if k in cls.__dataclass_fields__})
            except Exception:
                pass
        return cls()

    def save(self):
        """保存规则到 categories.json"""
        data = {}
        if RULES_FILE.exists():
            data = json.loads(RULES_FILE.read_text())
        data["rules"] = {k: v for k, v in asdict(self).items()}
        RULES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    @classmethod
    def list_presets(cls) -> List[dict]:
        """获取所有预设规则集"""
        if PRESETS_FILE.exists():
            try:
                data = json.loads(PRESETS_FILE.read_text())
                return data.get("presets", [])
            except Exception:
                pass
        return []

    def apply_preset(self, preset_id: str) -> bool:
        """应用指定的预设规则集"""
        presets = self.list_presets()
        for p in presets:
            if p["id"] == preset_id:
                for k, v in p["rules"].items():
                    if hasattr(self, k):
                        setattr(self, k, v)
                self.save()
                return True
        return False

    # ─── 筛选方法 ────────────────────────

    def filter_amazon_products(self, products: List[AmazonProduct]) -> tuple:
        """对 Amazon 商品列表应用发现阶段过滤规则。
        返回 (通过列表, 被过滤列表, 过滤原因映射)
        """
        passed = []
        filtered = []
        reasons = {}

        for p in products:
            reject_reasons = []

            if p.price is not None:
                if p.price < self.min_price:
                    reject_reasons.append(f"价格${p.price:.2f}低于最低${self.min_price:.0f}")
                elif p.price > self.max_price:
                    reject_reasons.append(f"价格${p.price:.2f}高于最高${self.max_price:.0f}")

            if p.rating is not None and p.rating < self.min_rating:
                reject_reasons.append(f"评分{p.rating}低于{self.min_rating}")

            if p.review_count is not None and p.review_count < self.min_reviews:
                reject_reasons.append(f"评论数{p.review_count}低于{self.min_reviews}")

            if p.rank > self.max_bsr_rank:
                reject_reasons.append(f"BSR#{p.rank}超出上限#{self.max_bsr_rank}")

            if self.require_prime and not p.is_prime:
                reject_reasons.append("非Prime商品")

            if reject_reasons:
                filtered.append(p)
                reasons[p.asin] = reject_reasons
            else:
                passed.append(p)

        return passed, filtered, reasons

    def filter_match_result(self, result: MatchResult) -> tuple:
        """对匹配结果应用规则过滤。返回 (是否通过, 原因)"""
        reasons = []

        if result.score < self.min_score:
            reasons.append(f"综合分{result.score:.0f}低于{self.min_score:.0f}")

        if result.price_diff_usd < self.min_profit_usd:
            reasons.append(f"利润${result.price_diff_usd:.2f}低于${self.min_profit_usd:.2f}")

        if result.estimated_profit_margin < self.min_profit_margin:
            reasons.append(
                f"利润率{result.estimated_profit_margin:.0f}%低于{self.min_profit_margin:.0f}%"
            )

        # 价差倍数
        amazon_price = result.amazon.price or 0
        alibaba_cost = result.total_cost_usd / max(result.alibaba.min_order_qty, 1)
        if alibaba_cost > 0:
            ratio = amazon_price / alibaba_cost
            if ratio < self.min_price_ratio:
                reasons.append(f"价差倍数{ratio:.1f}x低于{self.min_price_ratio:.1f}x")

        passed = len(reasons) == 0
        return passed, reasons

    def summary(self) -> dict:
        """人类可读的规则摘要"""
        return {
            "discover": {
                "价格范围": f"${self.min_price:.0f} - ${self.max_price:.0f}",
                "最低评分": f"{self.min_rating}+",
                "最低评论数": f"{self.min_reviews}+",
                "BSR排名上限": f"#{self.max_bsr_rank}以内",
                "仅Prime": "是" if self.require_prime else "否",
            },
            "match": {
                "最低价差倍数": f"{self.min_price_ratio}x",
                "最低单品利润": f"${self.min_profit_usd:.2f}",
                "最低利润率": f"{self.min_profit_margin}%",
                "最低推荐分": f"{self.min_score}",
            },
            "scoring": {
                "价差权重": self.price_diff_weight,
                "销量权重": self.sales_weight,
                "评分权重": self.rating_weight,
                "竞争权重": self.competition_weight,
            },
            "cost": {
                "人民币汇率": self.cny_to_usd,
                "落地成本系数": self.cost_multiplier,
            },
        }
