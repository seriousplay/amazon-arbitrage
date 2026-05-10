"""
Phase 2.1 验证 — 独立模式（避免 pydantic 依赖）
直接内联 TrendEngine + 数据模型逻辑
"""
import json
import math
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════
# 内联数据模型（与 app/models/trend.py 一致）
# ═══════════════════════════════════════════════════════

@dataclass
class TrendDataPoint:
    date: str
    value: float
    source: str = "bsr"
    def to_dict(self) -> dict:
        return {"date": self.date, "value": round(self.value, 1), "source": self.source}

@dataclass
class CategoryTrend:
    keyword: str
    current_score: float
    direction: str
    change_1m: float
    change_3m: float
    change_6m: float
    seasonality_peak: List[int]
    related_queries: List[str]
    source: str = "estimated"
    confidence: str = "medium"
    updated_at: str = ""
    time_series: List[TrendDataPoint] = field(default_factory=list)

    @property
    def trend_score(self) -> float:
        if self.direction == "up":
            if self.change_3m >= 20: return 5.0
            elif self.change_3m >= 10: return 4.0
            else: return 3.5
        elif self.direction == "down":
            if self.change_3m <= -15: return 1.0
            else: return 2.0
        else: return 3.0

    @property
    def label(self) -> str:
        if self.trend_score >= 4.5: return "🔥 高热度上升趋势"
        elif self.trend_score >= 3.5: return "📈 稳定上升"
        elif self.trend_score >= 2.5: return "➡️ 平稳"
        elif self.trend_score >= 1.5: return "📉 需求下降"
        return "⚠️ 热度骤降"

    @property
    def is_seasonal(self) -> bool:
        return len(self.seasonality_peak) > 0

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
            "source": self.source,
            "confidence": self.confidence,
            "updated_at": self.updated_at,
            "trend_score": self.trend_score,
            "label": self.label,
            "time_series": [p.to_dict() for p in self.time_series[-12:]],
        }

@dataclass
class TrendCache:
    updated_at: str = ""
    categories: Dict[str, CategoryTrend] = field(default_factory=dict)
    update_count: int = 0
    def to_dict(self) -> dict:
        return {
            "updated_at": self.updated_at,
            "update_count": self.update_count,
            "categories": {k: v.to_dict() for k, v in sorted(
                self.categories.items(), key=lambda x: x[1].current_score, reverse=True)},
        }


# ═══════════════════════════════════════════════════════
# 内建趋势数据（与 app/core/trends.py 一致）
# ═══════════════════════════════════════════════════════

BUILTIN_TRENDS_RAW: Dict[str, Tuple] = {
    "pet supplies":      (78, "up",   12, [],    ["dog food","cat toys","pet bed","pet carrier","pet bowls"]),
    "dog toys":          (72, "up",   8,  [],    ["chew toys","dog rope","squeaky toys","dog ball"]),
    "dog food":          (60, "flat", 1,  [],    ["dry dog food","puppy food","dog treats"]),
    "dog bed":           (68, "up",   10, [9,10,11,12], ["large dog bed","orthopedic dog bed","pet sofa"]),
    "cat litter":        (65, "flat", 2,  [],    ["clumping litter","scoop litter","cat litter box"]),
    "cat food":          (58, "up",   5,  [],    ["wet cat food","kitten food","cat treats"]),
    "cat tree":          (55, "up",   7,  [11,12], ["cat tower","cat condo","cat scratching post"]),
    "pet carrier":       (62, "up",   15, [5,6,7,12], ["dog carrier","cat carrier","travel pet carrier"]),
    "leash":             (70, "flat", 2,  [],    ["dog leash","retractable leash","pet harness"]),
    "pet bowl":          (55, "flat", 1,  [],    ["dog bowl","cat bowl","slow feeder"]),
    "camping tent":      (71, "up",   30, [3,4,5,6,7,8], ["family tent","backpacking tent","instant tent"]),
    "sleeping bag":      (63, "up",   25, [3,4,5,6,7,8,9], ["winter sleeping bag","camping sleeping bag","lightweight sleeping bag"]),
    "sunscreen":         (92, "up",   35, [5,6,7], ["sunblock","face sunscreen","sunscreen spray"]),
    "wireless earbuds":  (88, "up",   10, [],    ["bluetooth earbuds","true wireless","earbuds charging case"]),
    "phone case":        (90, "flat", -2, [],    ["silicone case","phone cover","shockproof case"]),
    "air fryer":         (55, "down", -8, [],    ["air fryer oven","basket air fryer","air fryer accessories"]),
    "yoga mat":          (71, "up",   15, [1,9], ["exercise mat","non slip yoga mat","thick yoga mat"]),
}


# ═══════════════════════════════════════════════════════
# 内联 TrendEngine
# ═══════════════════════════════════════════════════════

class TrendEngine:
    def __init__(self, cache_path: Optional[Path] = None):
        self._cache_path = cache_path or Path(tempfile.mktemp(suffix=".json"))
        self._cache = self._load_cache()
        self._last_update = time.time()

    def _load_cache(self) -> TrendCache:
        if self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text())
                cache = TrendCache(updated_at=data.get("updated_at",""), update_count=data.get("update_count",0))
                for kw, td in data.get("categories",{}).items():
                    ts = [TrendDataPoint(**p) for p in td.get("time_series",[])]
                    cache.categories[kw] = CategoryTrend(
                        keyword=td.get("keyword",kw), current_score=td.get("current_score",50),
                        direction=td.get("direction","flat"), change_1m=td.get("change_1m",0),
                        change_3m=td.get("change_3m",0), change_6m=td.get("change_6m",0),
                        seasonality_peak=td.get("seasonality_peak",[]),
                        related_queries=td.get("related_queries",[]),
                        source=td.get("source","builtin"), confidence=td.get("confidence","medium"),
                        updated_at=td.get("updated_at",""), time_series=ts,
                    )
                return cache
            except Exception:
                pass
        return self._build_defaults()

    def _build_defaults(self) -> TrendCache:
        now = datetime.now()
        cache = TrendCache(updated_at=now.isoformat(), update_count=1)
        for kw, (score, direction, change_3m, peaks, related) in BUILTIN_TRENDS_RAW.items():
            ts = self._generate_time_series(score, direction, change_3m)
            change_1m = self._compute_1m_change(ts)
            change_6m = self._compute_6m_change(ts)
            cache.categories[kw] = CategoryTrend(
                keyword=kw, current_score=float(score), direction=direction,
                change_1m=change_1m, change_3m=float(change_3m), change_6m=change_6m,
                seasonality_peak=peaks, related_queries=related,
                source="builtin", confidence="high" if direction!="flat" else "medium",
                updated_at=now.isoformat(), time_series=ts,
            )
        self._save_cache(cache)
        return cache

    def _generate_time_series(self, current_score: float, direction: str, change_3m: float) -> List[TrendDataPoint]:
        now = datetime.now()
        points = []
        if direction == "up":
            value_3m_ago = current_score / (1 + abs(change_3m) / 100)
        elif direction == "down":
            value_3m_ago = current_score * (1 + abs(change_3m) / 100)
        else:
            value_3m_ago = current_score
        monthly_delta = (current_score - value_3m_ago) / 3
        value_6m_ago = value_3m_ago - monthly_delta * 3
        for i in range(6):
            month_date = now - timedelta(days=30 * (5 - i))
            val = value_6m_ago + monthly_delta * i
            jitter = math.sin(i * 1.7) * 1.5
            points.append(TrendDataPoint(
                date=month_date.strftime("%Y-%m-%d"),
                value=round(max(0, min(100, val + jitter)), 1),
                source="builtin",
            ))
        return points

    def _compute_1m_change(self, ts: List[TrendDataPoint]) -> float:
        if len(ts) < 2: return 0.0
        return round((ts[-1].value - ts[-2].value) / max(ts[-2].value, 0.01) * 100, 1)

    def _compute_6m_change(self, ts: List[TrendDataPoint]) -> float:
        if len(ts) < 2: return 0.0
        return round((ts[-1].value - ts[0].value) / max(ts[0].value, 0.01) * 100, 1)

    def _save_cache(self, cache: Optional[TrendCache] = None):
        data = (cache or self._cache).to_dict()
        self._cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def get_trend(self, category: str = "", product_title: str = "") -> dict:
        keyword = self._match_keyword(category, product_title)
        trend = self._get_from_cache(keyword)
        if trend is None:
            trend = self._estimate_from_bsr(keyword or category)
        return self._to_compat_dict(trend)

    def _match_keyword(self, category: str, title: str = "") -> Optional[str]:
        combined = f"{category.lower()} {title.lower()}"
        if category:
            for kw in self._cache.categories:
                if kw in category.lower():
                    return kw
        candidates = []
        for kw in self._cache.categories:
            if kw in combined:
                candidates.append((self._cache.categories[kw].current_score, kw))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
        for kw in BUILTIN_TRENDS_RAW:
            if kw in combined:
                return kw
        return None

    def _get_from_cache(self, keyword: Optional[str]) -> Optional[CategoryTrend]:
        if not keyword: return None
        return self._cache.categories.get(keyword)

    def _estimate_from_bsr(self, keyword: str) -> CategoryTrend:
        now = datetime.now()
        ts = self._generate_time_series(50, "flat", 0)
        return CategoryTrend(keyword=keyword or "unknown", current_score=50.0,
            direction="flat", change_1m=0, change_3m=0, change_6m=0,
            seasonality_peak=[], related_queries=[], source="bsr_fallback",
            confidence="low", updated_at=now.isoformat(), time_series=ts)

    def _to_compat_dict(self, trend: CategoryTrend) -> dict:
        return {
            "matched_keyword": trend.keyword, "popularity": trend.current_score,
            "direction": trend.direction, "change_3m": trend.change_3m,
            "trend_score": trend.trend_score, "recommendation": trend.label,
            "change_1m": trend.change_1m, "change_6m": trend.change_6m,
            "seasonality_peak": trend.seasonality_peak,
            "related_queries": trend.related_queries[:5],
            "source": trend.source, "confidence": trend.confidence,
        }

    def list_all_trends(self) -> List[dict]:
        return [t.to_dict() for t in sorted(
            self._cache.categories.values(), key=lambda x: x.current_score, reverse=True)]

    @property
    def cache_info(self) -> dict:
        return {"categories": len(self._cache.categories), "updated_at": self._cache.updated_at}


import time  # for TrendEngine __init__


# ═══════════════════════════════════════════════════════
# 测试套件
# ═══════════════════════════════════════════════════════

def test_data_models():
    p = TrendDataPoint(date="2026-01-15", value=72.5)
    assert p.date == "2026-01-15" and p.value == 72.5
    d = p.to_dict()
    assert d == {"date": "2026-01-15", "value": 72.5, "source": "bsr"}
    print("  ✅ TrendDataPoint")

    t = CategoryTrend(keyword="test", current_score=78, direction="up",
        change_1m=2.5, change_3m=12, change_6m=18,
        seasonality_peak=[], related_queries=[])
    assert t.trend_score == 4.0
    assert t.label == "📈 稳定上升"
    assert not t.is_seasonal
    print("  ✅ CategoryTrend")

    cache = TrendCache(updated_at="2026-05-10T00:00:00")
    cache.categories["test"] = t
    d = cache.to_dict()
    assert "test" in d["categories"]
    print("  ✅ TrendCache")

def test_trend_scoring():
    cases = [
        (90, "up", 25, 5.0), (70, "up", 12, 4.0), (60, "up", 5, 3.5),
        (50, "flat", 0, 3.0), (40, "down", -10, 2.0), (30, "down", -20, 1.0),
    ]
    for score, direction, change_3m, expected in cases:
        t = CategoryTrend(keyword="t", current_score=score, direction=direction,
            change_1m=0, change_3m=change_3m, change_6m=0,
            seasonality_peak=[], related_queries=[])
        assert t.trend_score == expected, f"Got {t.trend_score} expected {expected}"
    print("  ✅ 6 种趋势分场景")

def test_seasonality():
    t1 = CategoryTrend(keyword="tent", current_score=70, direction="up",
        change_1m=5, change_3m=20, change_6m=30,
        seasonality_peak=[5,6,7,8], related_queries=[])
    assert t1.is_seasonal
    assert t1.trend_score == 5.0
    t2 = CategoryTrend(keyword="pet", current_score=78, direction="up",
        change_1m=2, change_3m=12, change_6m=18,
        seasonality_peak=[], related_queries=[])
    assert not t2.is_seasonal
    print("  ✅ 季节性检测")

def test_engine_init():
    engine = TrendEngine()
    assert len(engine._cache.categories) > 0
    pet = engine._cache.categories.get("pet supplies")
    assert pet is not None
    assert pet.current_score == 78.0
    assert len(pet.time_series) == 6
    print(f"  ✅ 引擎初始化: {len(engine._cache.categories)} 品类")

def test_time_series():
    engine = TrendEngine()
    pet = engine._cache.categories.get("pet supplies")
    ts = pet.time_series
    assert ts[0].value < ts[-1].value, "上升趋势应递增"
    print(f"  ✅ 上升时序: {ts[0].value:.0f} → {ts[-1].value:.0f}")
    # flat
    phone = engine._cache.categories.get("phone case")
    if phone:
        spread = max(p.value for p in phone.time_series) - min(p.value for p in phone.time_series)
        assert spread < 10, f"平稳品类 spread={spread}"
        print(f"  ✅ 平稳时序: spread={spread:.1f}")

def test_matching():
    engine = TrendEngine()
    r = engine.get_trend("Pet Supplies")
    assert r["matched_keyword"] == "pet supplies"
    assert r["trend_score"] > 0
    print(f"  ✅ 品类精确匹配: {r['matched_keyword']}")

    r = engine.get_trend(product_title="Orthopedic Dog Bed Medium")
    assert r["matched_keyword"] is not None
    print(f"  ✅ 标题匹配: {r['matched_keyword']}")

    r = engine.get_trend(product_title="Cat Litter Box Enclosed")
    assert r["matched_keyword"] in ("cat litter", "pet supplies")
    print(f"  ✅ 宠物子品类匹配: {r['matched_keyword']}")

def test_compat_dict():
    engine = TrendEngine()
    r = engine.get_trend("Pet Supplies")
    required = {"trend_score", "popularity", "direction", "change_3m", "matched_keyword", "recommendation", "source"}
    missing = required - set(r.keys())
    assert not missing, f"缺少: {missing}"
    print(f"  ✅ 兼容 dict: {len(r)} 字段, trend_score={r['trend_score']}")

def test_fallback():
    engine = TrendEngine()
    r = engine.get_trend("XYZUnknownCategory12345")
    assert r["trend_score"] == 3.0
    assert r["source"] == "bsr_fallback"
    print(f"  ✅ Fallback: {r['matched_keyword']}")

def test_list_all():
    engine = TrendEngine()
    all_t = engine.list_all_trends()
    assert len(all_t) >= 10
    assert all_t[0]["current_score"] >= all_t[-1]["current_score"]
    print(f"  ✅ list_all: {len(all_t)} 品类, 最高={all_t[0]['keyword']}={all_t[0]['current_score']}")

def test_cache_persistence():
    tmp = Path(tempfile.mktemp(suffix=".json"))
    try:
        e1 = TrendEngine(cache_path=tmp)
        assert tmp.exists()
        data = json.loads(tmp.read_text())
        assert len(data["categories"]) > 0
        print(f"  ✅ 缓存写入: {len(data['categories'])} 品类")

        e2 = TrendEngine(cache_path=tmp)
        assert len(e2._cache.categories) > 0
        assert e2.get_trend("Pet Supplies")["matched_keyword"] == "pet supplies"
        print(f"  ✅ 缓存读取验证")
    finally:
        if tmp.exists(): tmp.unlink()

def test_cache_info():
    engine = TrendEngine()
    info = engine.cache_info
    assert info["categories"] > 0
    assert info["updated_at"] != ""
    print(f"  ✅ cache_info: {info}")


if __name__ == "__main__":
    print("=" * 55)
    print("Phase 2.1 实时趋势引擎 — 独立验证")
    print("=" * 55)

    tests = [
        ("数据模型", test_data_models),
        ("趋势分计算", test_trend_scoring),
        ("季节性检测", test_seasonality),
        ("引擎初始化", test_engine_init),
        ("时序生成", test_time_series),
        ("关键词匹配", test_matching),
        ("兼容 Dict", test_compat_dict),
        ("Fallback", test_fallback),
        ("List All", test_list_all),
        ("缓存持久化", test_cache_persistence),
        ("Cache Info", test_cache_info),
    ]

    passed = 0
    for name, fn in tests:
        print(f"\n▶ {name}")
        try:
            fn()
            passed += 1
        except Exception as e:
            import traceback
            print(f"  ❌ 失败: {e}")
            traceback.print_exc()

    print(f"\n{'=' * 55}")
    print(f"结果: {passed}/{len(tests)} 通过")
    status = 0 if passed == len(tests) else 1
    print(f"{'🎉 全部通过!' if status == 0 else '⚠️ 有失败项'}")
    print("=" * 55)
    sys.exit(status)
