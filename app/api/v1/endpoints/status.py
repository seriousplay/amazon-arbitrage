"""
系统状态 API
"""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/status", tags=["系统状态"])


@router.get("/tasks")
async def list_tasks(request: Request):
    """列出所有运行中的任务"""
    scanner = getattr(request.app.state, "scanner", None)
    tasks = []
    if scanner:
        for task in scanner.list_tasks():
            tasks.append(
                {
                    "task_id": task.task_id,
                    "category": task.category,
                    "phase": task.phase.value if hasattr(task, 'phase') else "unknown",
                    "status": task.status,
                    "progress": task.progress,
                    "current_step": task.current_step,
                    "total": len(task.products) if hasattr(task, 'products') else 0,
                    "approved": task.approved_count if hasattr(task, 'approved_count') else 0,
                    "matched": task.matched_count if hasattr(task, 'matched_count') else 0,
                    "amazon": task.amazon_count if hasattr(task, 'amazon_count') else 0,
                    "matches": task.match_count if hasattr(task, 'match_count') else 0,
                }
            )
    return {"tasks": tasks, "total": len(tasks)}


@router.get("/login")
async def login_status(request: Request):
    """1688 登录状态"""
    scanner = getattr(request.app.state, "scanner", None)
    if not scanner or not hasattr(scanner, "alibaba_matcher"):
        return {"status": "unknown", "message": "匹配器未初始化"}

    matcher = scanner.alibaba_matcher
    status = matcher.login_status
    messages = {
        "ok": "已配置 1688 cookies，可进行真实搜索",
        "needs_cookies": "缺少 1688 cookies。请在 Chrome 登录 1688 后导出 cookies",
        "init_failed": "匹配器初始化失败，请检查 Playwright 和依赖",
    }
    return {
        "status": status,
        "message": messages.get(status, "未知"),
        "cookies_file": matcher.cookies_file,
    }


@router.get("/system")
async def system_status():
    """系统资源状态"""
    import os
    import psutil

    process = psutil.Process(os.getpid())
    mem = psutil.virtual_memory()
    return {
        "cpu_percent": psutil.cpu_percent(),
        "memory": {
            "used_mb": round(process.memory_info().rss / 1024**2, 1),
            "total_mb": round(mem.total / 1024**2, 1),
            "available_mb": round(mem.available / 1024**2, 1),
        },
        "disk_usage": {
            k: round(v / 1024**3, 1)
            for k, v in psutil.disk_usage("/")._asdict().items()
        },
    }
