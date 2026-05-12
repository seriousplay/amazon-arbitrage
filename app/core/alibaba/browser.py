"""
BrowserController - Playwright 浏览器生命周期管理

职责：
- 管理 Playwright 实例（启动/关闭）
- 管理浏览器上下文（browser context）
- 管理 cookies 持久化
- 提供全局单例模式（一个浏览器实例供所有搜索复用）
- 通过信号量控制并发访问
"""

import asyncio
import json
from pathlib import Path

from app.utils.logger import get_logger

logger = get_logger(__name__)

COOKIE_FILE = Path(__file__).parent.parent.parent.parent / "data" / "cookies" / "1688_cookies.json"


class BrowserController:
    """Playwright 浏览器控制器（全局单例）"""

    def __init__(self, headless: bool = True):
        """
        初始化浏览器控制器

        Args:
            headless: 是否无头模式
        """
        self.headless = headless
        self._has_cookies = COOKIE_FILE.exists()
        self._playwright = None
        self._browser = None
        self._browser_context = None

        # 并发控制
        self._browser_semaphore = asyncio.Semaphore(1)
        self._browser_lock = asyncio.Lock()

        if self._has_cookies:
            logger.info("✓ 1688 cookies 已找到")
        else:
            logger.warning(
                f"⚠ 1688 cookies 未找到: {COOKIE_FILE}\n"
                "  运行 python scripts/save_1688_cookies.py 获取 cookies"
            )

    @property
    def login_status(self) -> str:
        """检查登录状态"""
        return "ok" if self._has_cookies else "needs_cookies"

    @property
    def cookies_file(self) -> str:
        """返回 cookies 文件路径"""
        return str(COOKIE_FILE)

    async def ensure_browser(self):
        """
        确保浏览器已启动（惰性初始化）

        使用双重检查锁定模式防止并发初始化
        """
        if self._browser is not None:
            return

        async with self._browser_lock:
            if self._browser is not None:
                return  # 双重检查

            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                    "--disable-dev-shm-usage",
                ],
            )

            # 创建持久上下文
            self._browser_context = await self._browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="zh-CN",
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )

            # 加载 cookies
            if self._has_cookies:
                cookies = json.loads(COOKIE_FILE.read_text())
                if isinstance(cookies, list):
                    await self._browser_context.add_cookies(cookies)

            logger.info("✓ Playwright 浏览器已启动（全局单例）")

    async def new_page(self):
        """
        创建新页面（自动确保浏览器已启动）

        Returns:
            Playwright Page 对象
        """
        await self.ensure_browser()
        return await self._browser_context.new_page()

    async def cleanup(self):
        """清理浏览器资源"""
        if self._browser_context:
            await self._browser_context.close()
            self._browser_context = None

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        logger.info("✓ 浏览器资源已清理")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.ensure_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.cleanup()
        return False
