"""
结果 / 品类 / 调试 API
"""
from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/results", tags=["结果/品类/调试"])


def _get_scanner(request: Request):
    s = request.app.state.scanner
    if s is None:
        raise HTTPException(500, "引擎未初始化")
    return s


@router.get("/task/{task_id}")
async def get_task(request: Request, task_id: str):
    """获取任务完整状态（含商品清单和审核状态）"""
    scanner = _get_scanner(request)
    task = scanner.get_task(task_id)
    if not task:
        # 查历史
        storage = request.app.state.storage
        if storage:
            db = await storage.get_task(task_id)
            if db:
                db["phase"] = "done"
                db["products"] = []
                return db
        raise HTTPException(404, "任务不存在")

    products = []
    for dp in task.products:
        item = {
            "asin": dp.product.asin,
            "title": dp.product.title,
            "rank": dp.product.rank,
            "price": dp.product.price,
            "rating": dp.product.rating,
            "review_count": dp.product.review_count,
            "image_url": dp.product.image_url,
            "status": dp.status.value,
        }
        if dp.match_result:
            item["match"] = dp.match_result.model_dump()
        products.append(item)

    return {
        **task.to_summary(),
        "products": products,
        "breakout_results": task.breakout_results if hasattr(task, 'breakout_results') else [],
        "concentration_result": getattr(task, 'concentration_result', None),
        "new_product_analysis": getattr(task, 'new_product_analysis', None),
        "login_status": scanner.alibaba_matcher.login_status,
    }


@router.get("/categories")
async def list_categories(request: Request):
    return _get_scanner(request).load_categories()


@router.get("/review-analysis/{review_task_id}")
async def get_review_analysis(request: Request, review_task_id: str):
    """获取差评分析结果"""
    scanner = _get_scanner(request)
    result = scanner.get_review_analysis(review_task_id)
    if result is None:
        raise HTTPException(404, f"差评分析任务 {review_task_id} 不存在")
    return result


@router.get("/latest")
async def get_latest(request: Request, limit: int = 20):
    storage = request.app.state.storage
    if not storage:
        return {"results": [], "count": 0}
    results = await storage.list_recent_tasks(limit)
    return {"results": results, "count": len(results)}


@router.get("/debug-search")
async def debug_search(request: Request, keyword: str = Query(...)):
    """调试 1688 搜索：返回产品 + 响应诊断"""
    scanner = _get_scanner(request)
    try:
        products = await scanner.test_1688_search(keyword)
    except Exception as e:
        return {
            "keyword": keyword, "count": 0, "error": str(e),
            "login_status": scanner.alibaba_matcher.login_status,
            "cookies_loaded": scanner.alibaba_matcher._has_cookies,
        }

    debug = getattr(scanner.alibaba_matcher, '_last_debug', {})
    return {
        "keyword": keyword, "count": len(products),
        "login_status": scanner.alibaba_matcher.login_status,
        "cookies_loaded": scanner.alibaba_matcher._has_cookies,
        "products": products, "diagnostic": debug,
    }
