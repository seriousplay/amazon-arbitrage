"""
趋势分析数据模型 — 时序数据点 / 品类趋势 / 缓存
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TrendDataPoint:
    """时序数据点"""
    date: str            # ISO 日期 (YYYY-MM-DD)
    value: float         # 热度指数 (0-100)
    source: str = "bsr"  # 数据来源: bsr / google_trends / estimated

    def to_dict(self) -> dict:
        return {"date": self.date, "value": round(self.value, 1), "source": self.source}


@dataclass
class CategoryTrend:
    """单个品类的完整趋势信号"""
    keyword: str                        # 匹配到的关键词
    current_score: float                # 当前热度 (0-100)
    direction: str                      # 趋势方向: up / flat / down
    change_1m: float                    # 近 1 个月变化 (%)
    change_3m: float                    # 近 3 个月变化 (%)
    change_6m: float                    # 近 6 个月变化 (%)
    seasonality_peak: List[int]         # 季节性高峰月份 [1-12]
    related_queries: List[str]          # 相关热门搜索词
    competitor_count: int = 0           # 该品类下竞品数
    source: str = "estimated"           # 数据来源
    confidence: str = "medium"          # 置信度: high / medium / low
    updated_at: str = ""                # 最后更新时间 ISO
    time_series: List[TrendDataPoint] = field(default_factory=list)  # 近 6 月时序

    @property
    def trend_score(self) -> float:
        """转爆款评分用的 0-5 分"""
        if self.direction == "up":
            if self.change_3m >= 20:
                return 5.0
            elif self.change_3m >= 10:
                return 4.0
            else:
                return 3.5
        elif self.direction == "down":
            if self.change_3m <= -15:
                return 1.0
            else:
                return 2.0
        else:
            return 3.0

    @property
    def label(self) -> str:
        """人类可读的趋势标签"""
        if self.trend_score >= 4.5:
            return "🔥 高热度上升趋势"
        elif self.trend_score >= 3.5:
            return "📈 稳定上升"
        elif self.trend_score >= 2.5:
            return "➡️ 平稳"
        elif self.trend_score >= 1.5:
            return "📉 需求下降"
        return "⚠️ 热度骤降"

    @property
    def is_seasonal(self) -> bool:
        """是否为强季节性品类"""
        return len(self.seasonality_peak) > 0 and (
            max(self.seasonality_peak, key=self.seasonality_peak.count)
            if self.seasonality_peak else False
        )

    def to_dict(self) -> dict:
        return {
            "keyword": self.keyword,
            "current_score": round(self.current_score, 1),
            "direction": self.direction,
            "change_1m": round(self.change_1m, 1),
            "change_3m": round(self.change_3m, 1),
            "change_6m": round(self.change_6m, 1),
            "seasonality_peak": self.seasonality_peak,
            "related_queries": self.related_queries[:10],
            "competitor_count": self.competitor_count,
            "source": self.source,
            "confidence": self.confidence,
            "updated_at": self.updated_at,
            "trend_score": self.trend_score,
            "label": self.label,
            "time_series": [p.to_dict() for p in self.time_series[-12:]],
        }


@dataclass
class TrendCache:
    """趋势缓存容器"""
    updated_at: str = ""                     # 整体刷新时间 ISO
    categories: Dict[str, CategoryTrend] = field(default_factory=dict)
    update_count: int = 0

    def to_dict(self) -> dict:
        return {
            "updated_at": self.updated_at,
            "update_count": self.update_count,
            "categories": {
                k: v.to_dict() for k, v in sorted(
                    self.categories.items(),
                    key=lambda x: x[1].current_score,
                    reverse=True,
                )
            },
        }
