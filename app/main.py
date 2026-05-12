"""
Amazon Pet Supplies Arbitrage Scout — Web 应用主入口
基于 FastAPI 构建，支持 REST API + 前端管理页面
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import ensure_directories, settings
from app.core.scanner import ScanEngine
from app.core.scheduler import InAppScheduler
from app.services.storage import StorageService
from app.workers.scanner_worker import ScannerWorker
from app.api.v1.endpoints.scan import router as scan_router
from app.api.v1.endpoints.results import router as results_router
from app.api.v1.endpoints.status import router as status_router
from app.utils.logger import get_logger

STATIC_DIR = Path(__file__).parent / "static"

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动初始化
    logger.info("=" * 60)
    logger.info(f"启动 {settings.APP_NAME} v{settings.VERSION}")
    logger.info(f"环境: {settings.ENVIRONMENT} | 数据库: {settings.DATABASE_URL}")
    logger.info("=" * 60)

    ensure_directories()

    # 初始化存储服务
    app.state.storage = StorageService(settings.DATABASE_URL)
    await app.state.storage.initialize()

    # 初始化扫描引擎
    app.state.scanner = ScanEngine(
        storage=app.state.storage,
        config=settings,
    )

    # 启动后台 worker
    app.state.worker = ScannerWorker(
        scanner=app.state.scanner,
        max_workers=settings.MAX_WORKERS,
    )
    await app.state.worker.start()

    # 启动定时调度器
    app.state.scheduler = InAppScheduler()
    app.state.scheduler.set_scan_callback(
        lambda cat, n: app.state.scanner.start_quick_scan(category=cat, max_products=n)
    )
    await app.state.scheduler.start()

    logger.info("✓ 应用启动完成")
    yield

    # 关闭清理
    logger.info("应用关闭中...")
    await app.state.scheduler.stop()
    await app.state.worker.stop()
    await app.state.scanner.cleanup()
    await app.state.storage.close()
    logger.info("✓ 清理完成")


app = FastAPI(
    title="Amazon Pet Arbitrage Scout",
    description="亚马逊宠物用品套利智能扫描系统 — 跨平台价差发现引擎",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置（生产环境应从 .env 读取精确域名）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(scan_router, prefix="/api/v1")
app.include_router(results_router, prefix="/api/v1")
app.include_router(status_router, prefix="/api/v1")

# 前端静态文件
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "running",
        "docs": "/docs",
        "app": "/app",
        "api": "/api/v1",
    }


@app.get("/app")
async def spa():
    """前端管理页面"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"error": "前端页面未找到，请确认 app/static/index.html 存在"}


@app.get("/health")
async def health_check():
    storage = getattr(app.state, "storage", None)
    worker = getattr(app.state, "worker", None)
    return {
        "status": "healthy",
        "database": "connected" if storage and storage.is_connected else "disconnected",
        "worker": "running" if worker and worker.is_running else "stopped",
    }
