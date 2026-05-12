"""
AlibabaMatcher - 1688 匹配器（Facade）

职责：
- 对外提供统一的匹配接口
- 组合 BrowserController、CaptchaSolver、SearchHandler
- 提供简单的 search_and_match API
- 管理浏览器生命周期
"""

import logging
from typing import List, Optional

from app.models.product import AlibabaProduct as PydanticAlibabaProduct
from app.core.alibaba.browser import BrowserController
from app.core.alibaba.captcha import CaptchaSolver
from app.core.alibaba.search import SearchHandler
from app.config import settings

logger = logging.getLogger(__name__)


class AlibabaMatcher:
    """
    1688 商品匹配器

    Facade 模式：组合 BrowserController、CaptchaSolver、SearchHandler，
    对外提供简洁的 search_and_match 接口。
    """

    def __init__(self, config=settings, use_browser: bool = True):
        """
        初始化 AlibabaMatcher

        Args:
            config: 配置对象
            use_browser: 是否使用浏览器模式
        """
        self.config = config
        self.use_browser = use_browser

        # 初始化组件
        headless = getattr(config, "PLAYWRIGHT_HEADLESS", True)
        self.browser_controller = BrowserController(headless=headless)

        captcha_confidence = getattr(config, "CAPTCHA_CONFIDENCE_THRESHOLD", 0.8)
        captcha_debug = getattr(config, "CAPTCHA_DEBUG", False)
        self.captcha_solver = CaptchaSolver(
            debug=captcha_debug,
            confidence_threshold=captcha_confidence,
        )

        self.search_handler = SearchHandler(
            browser_controller=self.browser_controller,
            use_browser=use_browser,
        )

    async def _ensure_browser(self):
        """确保浏览器已启动"""
        await self.browser_controller.ensure_browser()

    @property
    def login_status(self) -> str:
        """检查登录状态"""
        return self.browser_controller.login_status

    @property
    def cookies_file(self) -> str:
        """返回 cookies 文件路径"""
        return self.browser_controller.cookies_file

    async def search_and_match(
        self,
        keyword: str,
        category: Optional[str] = None,
        category_path: Optional[str] = None,
    ) -> List[PydanticAlibabaProduct]:
        """
        搜索并匹配 1688 商品

        Args:
            keyword: 搜索关键词
            category: Amazon 类目名
            category_path: Amazon 完整类目路径

        Returns:
            匹配的 AlibabaProduct 列表
        """
        try:
            # 构建搜索关键词
            search_keyword = self.search_handler.build_search_keyword(
                title=keyword,
                category=category,
                category_path=category_path,
            )

            if not search_keyword:
                logger.warning(f"无法构建搜索关键词: {keyword}")
                return []

            # 执行搜索
            results = await self.search_handler.search(search_keyword, max_results=20)

            return results

        except Exception as e:
            logger.error(f"搜索并匹配失败: {e}")
            return []

    async def match_amazon_product(
        self,
        product,
    ) -> Optional[PydanticAlibabaProduct]:
        """
        为单个 Amazon 产品匹配 1688 商品

        Args:
            product: AmazonProduct

        Returns:
            最佳匹配的 AlibabaProduct，如果没有找到则返回 None
        """
        results = await self.search_and_match(
            keyword=product.title,
            category=product.category,
            category_path=product.category_path,
        )

        if not results:
            return None

        # 返回最佳匹配（第一个结果）
        return results[0]

    async def cleanup(self):
        """清理资源"""
        await self.browser_controller.cleanup()

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self._ensure_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.cleanup()
        return False
