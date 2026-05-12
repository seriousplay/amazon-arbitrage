"""
BrowserPool - 浏览器池服务

职责：
- 管理 Playwright 浏览器实例池
- 控制并发访问（信号量限制）
- 提供浏览器上下文的获取和释放
- 生命周期管理（创建、销毁、错误恢复）

与旧的全局单例模式不同，BrowserPool 支持：
- 多个浏览器实例（可配置 pool_size）
- 并发控制（通过 asyncio.Semaphore）
- 优雅的初始化和清理
- 更好的错误隔离和恢复
"""

import asyncio
from typing import List, Optional, Protocol
from pathlib import Path
import logging

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from app.config import settings

logger = logging.getLogger(__name__)


class BrowserPoolConfig:
    """浏览器池配置"""

    def __init__(
        self,
        headless: bool = True,
        pool_size: int = 2,
        timeout: int = 30000,
        user_data_dir: Optional[Path] = None,
    ):
        self.headless = headless
        self.pool_size = pool_size
        self.timeout = timeout
        self.user_data_dir = user_data_dir


class BrowserPool:
    """
    Playwright 浏览器池

    管理多个浏览器实例，通过信号量控制并发访问。
    支持配置池大小、无头模式、超时等参数。

    使用示例:
        ```python
        pool = BrowserPool(config=BrowserPoolConfig(pool_size=2))

        # 获取浏览器上下文
        async with pool.acquire() as context:
            page = await context.new_page()
            await page.goto("https://example.com")

        # 清理
        await pool.close_all()
        ```
    """

    def __init__(self, config: Optional[BrowserPoolConfig] = None):
        """
        初始化浏览器池

        Args:
            config: 浏览器池配置，如果为 None 则使用默认配置
        """
        self.config = config or BrowserPoolConfig(
            headless=getattr(settings, "PLAYWRIGHT_HEADLESS", True),
            pool_size=getattr(settings, "BROWSER_CONCURRENCY", 2),
            timeout=getattr(settings, "PLAYWRIGHT_TIMEOUT", 30000),
        )
        self._browsers: List[Browser] = []
        self._semaphore = asyncio.Semaphore(self.config.pool_size)
        self._playwright = None
        self._lock = asyncio.Lock()
        self._closed = False

    async def _ensure_playwright(self):
        """确保 Playwright 实例已启动"""
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            logger.info("Playwright 实例已启动")

    async def _create_browser(self) -> Browser:
        """
        创建新的浏览器实例

        Returns:
            新创建的 Browser 实例
        """
        await self._ensure_playwright()

        launch_options = {
            "headless": self.config.headless,
            "args": [
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        }

        if self.config.user_data_dir:
            launch_options["user_data_dir"] = str(self.config.user_data_dir)

        browser = await self._playwright.chromium.launch(**launch_options)
        logger.debug(f"创建新浏览器实例（池大小: {len(self._browsers)+1}/{self.config.pool_size}）")
        return browser

    async def acquire(self) -> BrowserContext:
        """
        获取浏览器上下文（自动管理浏览器实例）

        如果池中有空闲浏览器，直接返回其上下文。
        如果池已满，等待直到有空闲浏览器。

        Returns:
            浏览器上下文

        Raises:
            RuntimeError: 如果浏览器池已关闭
        """
        if self._closed:
            raise RuntimeError("浏览器池已关闭，无法获取上下文")

        async with self._semaphore:
            # 尝试复用现有浏览器
            for browser in self._browsers:
                try:
                    context = await browser.new_context(
                        viewport={"width": 1920, "height": 1080},
                        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    )
                    logger.debug(f"复用浏览器上下文（活跃: {len(self._browsers)}）")
                    return context
                except Exception as e:
                    logger.warning(f"复用浏览器失败: {e}，尝试创建新浏览器")
                    # 移除失效的浏览器
                    self._browsers.remove(browser)

            # 创建新浏览器
            browser = await self._create_browser()
            self._browsers.append(browser)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            )
            return context

    async def release(self, context: BrowserContext) -> None:
        """
        释放浏览器上下文

        关闭上下文但不关闭底层浏览器，允许复用。

        Args:
            context: 要释放的浏览器上下文
        """
        try:
            await context.close()
        except Exception as e:
            logger.warning(f"关闭浏览器上下文时出错: {e}")

    async def close_browser(self, browser: Browser) -> None:
        """
        关闭指定浏览器并从池中移除

        Args:
            browser: 要关闭的浏览器实例
        """
        try:
            await browser.close()
            if browser in self._browsers:
                self._browsers.remove(browser)
            logger.debug(f"关闭浏览器（剩余: {len(self._browsers)}）")
        except Exception as e:
            logger.warning(f"关闭浏览器时出错: {e}")

    async def close_all(self) -> None:
        """关闭池中所有浏览器并清理资源"""
        if self._closed:
            return

        self._closed = True

        # 关闭所有浏览器
        close_tasks = [browser.close() for browser in self._browsers]
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)

        self._browsers.clear()

        # 关闭 Playwright
        if self._playwright:
            try:
                await self._playwright.stop()
                logger.info("Playwright 实例已停止")
            except Exception as e:
                logger.warning(f"停止 Playwright 时出错: {e}")
            finally:
                self._playwright = None

    @property
    def active_browsers(self) -> int:
        """当前活跃的浏览器数量"""
        return len(self._browsers)

    @property
    def available_slots(self) -> int:
        """可用插槽数（可同时执行的并发数）"""
        return self._semaphore._value

    async def __aenter__(self) -> "BrowserPool":
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.close_all()


class BrowserPoolManager:
    """
    浏览器池管理器（单例模式）

    管理全局唯一的浏览器池，避免重复创建浏览器实例。
    适合在整个应用生命周期中复用。

    使用示例:
        ```python
        pool = BrowserPoolManager.get_instance()
        await pool.initialize(config)

        # 在请求处理中使用
        async with pool.acquire_context() as context:
            page = await context.new_page()
            # ...

        # 应用关闭时清理
        await pool.shutdown()
        ```
    """

    _instance: Optional["BrowserPoolManager"] = None
    _pool: Optional[BrowserPool] = None

    def __init__(self):
        if BrowserPoolManager._instance is not None:
            raise RuntimeError("使用 BrowserPoolManager.get_instance() 获取实例")
        self._pool = None

    @classmethod
    def get_instance(cls) -> "BrowserPoolManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例（主要用于测试）"""
        if cls._instance and cls._instance._pool:
            # 注意：这里需要异步关闭，但 reset_instance 是同步方法
            # 实际使用时需要在异步上下文中手动关闭
            pass
        cls._instance = None

    async def initialize(self, config: Optional[BrowserPoolConfig] = None) -> None:
        """
        初始化浏览器池

        Args:
            config: 浏览器池配置
        """
        if self._pool is not None:
            logger.warning("浏览器池已初始化，跳过")
            return

        self._pool = BrowserPool(config)
        logger.info("浏览器池管理器已初始化")

    async def get_pool(self) -> BrowserPool:
        """
        获取浏览器池实例

        Returns:
            浏览器池

        Raises:
            RuntimeError: 如果浏览器池未初始化
        """
        if self._pool is None:
            raise RuntimeError("浏览器池未初始化，请先调用 initialize()")
        return self._pool

    async def shutdown(self) -> None:
        """关闭浏览器池"""
        if self._pool:
            await self._pool.close_all()
            self._pool = None
            logger.info("浏览器池管理器已关闭")
