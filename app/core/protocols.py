"""
Protocol Interfaces - 核心抽象接口

定义关键服务的协议（Protocol），实现依赖倒置原则：
- 高层模块不依赖低层模块，两者都依赖抽象
- 抽象不依赖细节，细节依赖抽象

这使得：
- 测试更容易（可以轻松创建 mock 实现）
- 实现可以互换（如替换不同的爬虫或匹配器）
- 架构更清晰（明确各组件契约）
"""

from typing import Protocol, List, Optional, runtime_checkable
from app.models.product import AmazonProduct, AlibabaProduct, MatchResult


class Spider(Protocol):
    """Amazon 产品爬虫协议"""

    async def scrape(
        self,
        category: str,
        max_products: int,
    ) -> List[AmazonProduct]:
        """
        爬取 Amazon 产品

        Args:
            category: 产品类目
            max_products: 最大爬取数量

        Returns:
            爬取到的 Amazon 产品列表
        """
        ...


class Matcher(Protocol):
    """1688 商品匹配器协议"""

    async def search_and_match(
        self,
        title: str,
        category: Optional[str] = None,
    ) -> Optional[AlibabaProduct]:
        """
        搜索并匹配 1688 商品

        Args:
            title: Amazon 产品标题
            category: 产品类目（可选，用于优化搜索）

        Returns:
            匹配到的 AlibabaProduct，未找到则返回 None
        """
        ...


class Scorer(Protocol):
    """匹配分数计算器协议"""

    def calculate_score(
        self,
        amazon: AmazonProduct,
        alibaba: AlibabaProduct,
    ) -> MatchResult:
        """
        计算 Amazon-Alibaba 匹配分数

        Args:
            amazon: Amazon 产品
            alibaba: 1688 产品

        Returns:
            包含分数和详细信息的 MatchResult
        """
        ...


class Storage(Protocol):
    """数据存储协议"""

    async def save_products(
        self,
        task_id: str,
        products: List[AmazonProduct],
    ) -> None:
        """保存产品列表"""
        ...

    async def save_match_results(
        self,
        task_id: str,
        results: List[MatchResult],
    ) -> None:
        """保存匹配结果"""
        ...

    async def get_task_results(self, task_id: str) -> Optional[dict]:
        """获取任务结果"""
        ...


@runtime_checkable
class BrowserContext(Protocol):
    """浏览器上下文协议（用于 Playwright）"""

    async def new_page(self):
        """创建新页面"""
        ...

    async def close(self):
        """关闭上下文"""
        ...

    async def cookies(self) -> List[dict]:
        """获取 cookies"""
        ...

    async def add_cookies(self, cookies: List[dict]) -> None:
        """添加 cookies"""
        ...


@runtime_checkable
class BrowserController(Protocol):
    """浏览器控制器协议"""

    async def ensure_browser(self) -> None:
        """确保浏览器已初始化"""
        ...

    async def new_page(self):
        """创建新页面（自动关联到上下文）"""
        ...

    async def cleanup(self) -> None:
        """清理浏览器资源"""
        ...

    @property
    def is_initialized(self) -> bool:
        """浏览器是否已初始化"""
        ...
