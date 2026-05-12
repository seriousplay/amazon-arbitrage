"""
扫描任务 API — 发现 / 审核 / 匹配
"""
import inspect

from fastapi import APIRouter, HTTPException, Request

from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/scan", tags=["扫描任务"])


def _get_scanner(request: Request):
    s = request.app.state.scanner
    if s is None:
        raise HTTPException(500, "引擎未初始化")
    return s


# ═══════════════════════════════════════════════════════
# 规则管理（必须在 /{task_id} 之前，避免路由冲突）
# ═══════════════════════════════════════════════════════

@router.get("/rules")
async def get_rules(request: Request):
    scanner = _get_scanner(request)
    return scanner.rules.summary()


@router.get("/rules/raw")
async def get_rules_raw(request: Request):
    from dataclasses import asdict
    return asdict(_get_scanner(request).rules)


@router.post("/rules")
async def update_rules(request: Request):
    body = await request.json()
    scanner = _get_scanner(request)
    from dataclasses import fields
    valid = {f.name for f in fields(scanner.rules)}
    for k, v in body.items():
        if k in valid:
            setattr(scanner.rules, k, v)
    scanner.rules.save()
    return {"success": True}


@router.get("/rules/presets")
async def list_presets(request: Request):
    """获取所有预设规则集"""
    import json
    from pathlib import Path
    presets_file = Path(__file__).parents[4] / "data" / "rule_presets.json"
    if presets_file.exists():
        try:
            return json.loads(presets_file.read_text()).get("presets", [])
        except Exception:
            pass
    return []


@router.post("/rules/presets/{preset_id}")
async def apply_preset(request: Request, preset_id: str):
    """应用指定预设规则集"""
    import json
    from pathlib import Path
    presets_file = Path(__file__).parents[4] / "data" / "rule_presets.json"
    if not presets_file.exists():
        raise HTTPException(404, "预设文件不存在")

    presets = json.loads(presets_file.read_text()).get("presets", [])
    for p in presets:
        if p["id"] == preset_id:
            scanner = _get_scanner(request)
            for k, v in p["rules"].items():
                if hasattr(scanner.rules, k):
                    setattr(scanner.rules, k, v)
            scanner.rules.save()
            return {"success": True, "preset": preset_id}
    raise HTTPException(404, f"预设 '{preset_id}' 不存在")


# ═══════════════════════════════════════════════════════
# 两阶段扫描：发现 → 匹配（独立执行）
# ═══════════════════════════════════════════════════════

@router.post("/discover-only")
async def start_discover_only(
    request: Request, category: str = "Pet Supplies",
    max_products: int = 15, bsr_url: str = None,
):
    """阶段1：仅 Amazon 发现（不含 1688 匹配）"""
    scanner = _get_scanner(request)
    task_id = await scanner.start_discover_only(
        category=category, max_products=max_products, bsr_url=bsr_url,
    )
    return {"success": True, "task_id": task_id, "phase": "discover"}


@router.post("/cancel-all")
async def cancel_all_scans(request: Request):
    """取消所有正在运行的扫描任务"""
    scanner = _get_scanner(request)
    count = await scanner.cancel_all()
    return {"success": True, "cancelled": count, "message": f"已取消 {count} 个任务"}


@router.post("/{task_id}/match-now")
async def match_now(request: Request, task_id: str):
    """阶段2：对已发现商品执行 1688 匹配"""
    scanner = _get_scanner(request)
    ok = await scanner.start_match_only(task_id)
    if not ok:
        raise HTTPException(400, "无可匹配商品，请先执行发现阶段")
    return {"success": True, "task_id": task_id, "phase": "matching"}


# ═══════════════════════════════════════════════════════
# 一键扫描（推荐）
# ═══════════════════════════════════════════════════════

@router.post("/")
async def start_scan(
    request: Request, category: str = "Pet Supplies",
    max_products: int = 15, bsr_url: str = None,
):
    """兼容旧版入口：等同于 quick-scan。"""
    scanner = _get_scanner(request)
    if "start_scan" in vars(scanner):
        result = scanner.start_scan(category=category, max_products=max_products)
    else:
        result = scanner.start_quick_scan(
            category=category, max_products=max_products, bsr_url=bsr_url,
        )
    task_id = await result if inspect.isawaitable(result) else result
    return {"success": True, "task_id": task_id, "mode": "quick"}


@router.post("/quick-scan")
async def start_quick_scan(
    request: Request, category: str = "Pet Supplies",
    max_products: int = 15, bsr_url: str = None,
):
    """一键扫描：自动发现 + 匹配 + 高价值筛选"""
    scanner = _get_scanner(request)
    task_id = await scanner.start_quick_scan(
        category=category, max_products=max_products, bsr_url=bsr_url,
    )
    return {"success": True, "task_id": task_id, "mode": "quick"}


@router.post("/deep-discover")
async def start_deep_discover(
    request: Request, category: str = "Pet Supplies",
    max_products: int = 100, bsr_url: str = None,
):
    """深度市场分析：爬取 Top 100 BSR + 品牌集中度 + 价格区间分析"""
    scanner = _get_scanner(request)
    task_id = await scanner.start_deep_discover(
        category=category, max_products=max_products, bsr_url=bsr_url,
    )
    return {
        "success": True, "task_id": task_id, "mode": "deep_discover",
        "message": "深度爬取 Top 100 并分析市场集中度，预计 3-5 分钟完成",
    }


# ═══════════════════════════════════════════════════════
# 差评分析
# ═══════════════════════════════════════════════════════

@router.post("/review-analysis")
async def start_review_analysis(
    request: Request, asins: str = "",
    category: str = "Pet Supplies",
):
    """差评分析：爬取指定 ASIN 的 1-3 星评论并做缺陷聚类分析

    asins: 逗号分隔的 ASIN 列表，如 "B00EXAMPLE1,B00EXAMPLE2"
    """
    scanner = _get_scanner(request)
    if not asins.strip():
        raise HTTPException(400, "请提供至少一个 ASIN")

    asin_list = [a.strip() for a in asins.split(",") if a.strip()]
    if len(asin_list) > 10:
        raise HTTPException(400, "单次最多分析 10 个 ASIN")

    task_id = await scanner.start_review_analysis(
        asins=asin_list, category=category,
    )
    return {
        "success": True, "task_id": task_id,
        "mode": "review_analysis",
        "asin_count": len(asin_list),
        "message": f"正在分析 {len(asin_list)} 个产品的差评，预计 2-5 分钟",
    }


@router.post("/review-analysis-from-task")
async def review_analysis_from_task(
    request: Request, task_id: str, max_asins: int = 5,
):
    """从已有扫描任务中取 ASIN 进行差评分析"""
    scanner = _get_scanner(request)
    task = scanner.get_task(task_id)
    if not task:
        raise HTTPException(404, f"任务 {task_id} 不存在")

    asins = []
    for dp in task.products:
        if len(asins) >= max_asins:
            break
        asins.append(dp.product.asin)

    if not asins:
        raise HTTPException(400, "任务中无商品数据")

    new_task_id = await scanner.start_review_analysis(
        asins=asins, category=task.category,
    )
    return {
        "success": True, "task_id": new_task_id,
        "source_task": task_id, "asin_count": len(asins),
        "message": f"正在分析 {len(asins)} 个产品的差评",
    }


# ═══════════════════════════════════════════════════════
# 定时任务管理
# ═══════════════════════════════════════════════════════

@router.get("/schedule")
async def get_schedule(request: Request):
    """获取定时任务配置"""
    scheduler = getattr(request.app.state, "scheduler", None)
    if not scheduler:
        return {"error": "调度器未启动"}
    return {
        "tasks": scheduler.tasks,
        "last_runs": scheduler.last_runs,
    }


@router.post("/schedule/{task_id}/toggle")
async def toggle_schedule(request: Request, task_id: str, enabled: bool = True):
    """启用/禁用定时任务"""
    scheduler = getattr(request.app.state, "scheduler", None)
    if not scheduler:
        raise HTTPException(500, "调度器未启动")
    scheduler.toggle_task(task_id, enabled)
    return {"success": True, "task_id": task_id, "enabled": enabled}


@router.post("/schedule/{task_id}/run-now")
async def run_schedule_now(request: Request, task_id: str):
    """立即执行定时任务"""
    scheduler = getattr(request.app.state, "scheduler", None)
    if not scheduler:
        raise HTTPException(500, "调度器未启动")
    ok = await scheduler.run_now(task_id)
    if not ok:
        raise HTTPException(404, f"任务 '{task_id}' 不存在")
    return {"success": True, "task_id": task_id}


@router.post("/schedule/update")
async def update_schedule(request: Request):
    """更新定时任务配置"""
    body = await request.json()
    scheduler = getattr(request.app.state, "scheduler", None)
    if not scheduler:
        raise HTTPException(500, "调度器未启动")
    for task_id, config in body.items():
        scheduler.update_task(task_id, config)
    return {"success": True}


# ═══════════════════════════════════════════════════════
# 趋势引擎 API
# ═══════════════════════════════════════════════════════

@router.get("/trends")
async def list_trends(request: Request):
    """列出所有缓存品类趋势（按热度降序）"""
    scanner = _get_scanner(request)
    return {
        "trends": scanner.list_trends(),
        "cache_info": scanner.trend_engine.cache_info,
    }


@router.get("/trends/{keyword}")
async def get_trend(request: Request, keyword: str):
    """获取指定品类的趋势详情"""
    scanner = _get_scanner(request)
    result = scanner.get_trend(keyword)
    if result is None:
        raise HTTPException(404, f"品类 '{keyword}' 不在趋势缓存中")
    return result


@router.post("/trends/refresh")
async def refresh_trends(request: Request):
    """用内建数据刷新趋势缓存"""
    scanner = _get_scanner(request)
    result = scanner.refresh_trends()
    return result


@router.post("/trends/{keyword}/refresh")
async def refresh_single_trend(request: Request, keyword: str):
    """从网络更新指定品类趋势数据"""
    scanner = _get_scanner(request)
    result = await scanner.update_trend_from_web(keyword)
    return result


# ═══════════════════════════════════════════════════════
# Phase 1: 发现（传统分步模式）
# ═══════════════════════════════════════════════════════

@router.post("/discover")
async def start_discover(
    request: Request, category: str = "Pet Supplies",
    max_products: int = 20, bsr_url: str = None,
):
    scanner = _get_scanner(request)
    task_id = await scanner.start_discover(
        category=category, max_products=max_products, bsr_url=bsr_url,
    )
    return {"success": True, "task_id": task_id, "phase": "review"}


# ═══════════════════════════════════════════════════════
# Phase 2: 审核（/{task_id}/... 必须在最后）
# ═══════════════════════════════════════════════════════

@router.post("/{task_id}/approve/{asin}")
async def approve_product(request: Request, task_id: str, asin: str):
    scanner = _get_scanner(request)
    if not scanner.approve_product(task_id, asin):
        raise HTTPException(404, "任务不存在或不在审核阶段")
    return {"success": True}


@router.post("/{task_id}/reject/{asin}")
async def reject_product(request: Request, task_id: str, asin: str):
    scanner = _get_scanner(request)
    if not scanner.reject_product(task_id, asin):
        raise HTTPException(404, "任务不存在或不在审核阶段")
    return {"success": True}


@router.post("/{task_id}/approve-all")
async def approve_all(request: Request, task_id: str):
    scanner = _get_scanner(request)
    task = scanner.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.phase.value not in ("review", "done"):
        raise HTTPException(400, f"当前阶段为 {task.phase.value}")
    count = scanner.approve_all_products(task_id)
    return {"success": True, "approved_count": count, "phase": task.phase.value}


@router.get("/{task_id}/product/{asin}/detail")
async def product_detail(request: Request, task_id: str, asin: str):
    scanner = _get_scanner(request)
    task = scanner.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    product = None
    for dp in task.products:
        if dp.product.asin == asin:
            product = dp.product
            break
    if not product:
        raise HTTPException(404, "产品不存在")

    translation = scanner.alibaba_matcher.translate_keyword(product.title)
    ali_products = await scanner.alibaba_matcher.search_and_match(
        product.title, category_path=product.category_path
    )

    return {
        "asin": product.asin, "title": product.title,
        "brand": product.brand, "category_path": product.category_path,
        "chinese_keywords": translation["chinese"], "keywords": translation["keywords"],
        "rank": product.rank, "price": product.price,
        "rating": product.rating, "review_count": product.review_count,
        "amazon_url": f"https://www.amazon.com/dp/{product.asin}",
        "alibaba_count": len(ali_products),
        "alibaba_products": [p.model_dump() for p in ali_products],
        "login_status": scanner.alibaba_matcher.login_status,
    }


# ═══════════════════════════════════════════════════════
# Phase 3: 匹配
# ═══════════════════════════════════════════════════════

@router.post("/{task_id}/match")
async def start_matching(request: Request, task_id: str):
    scanner = _get_scanner(request)
    ok = await scanner.start_matching(task_id)
    if not ok:
        raise HTTPException(400, "无已审核商品或任务不在审核阶段")
    task = scanner.get_task(task_id)
    return {
        "success": True, "task_id": task_id,
        "approved_count": task.approved_count if task else 0,
        "phase": "matching",
    }
