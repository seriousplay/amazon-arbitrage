"""
DiscoveryService - Amazon 产品发现服务

职责：
- 调用 Amazon BSR Spider 爬取产品
- 根据规则过滤产品
- 返回经过滤的 AmazonProduct 列表
"""

from typing import List, Optional

from app.models.product import AmazonProduct
from app.core.scanner import ScanTask, DiscoveredProduct, ProductStatus
from app.core.rules import RulesConfig
from app.core.amazon_spider import AmazonBSRSpider
from app.config import settings


class DiscoveryService:
    """Amazon BSR 产品发现服务"""

    def __init__(self, spider: AmazonBSRSpider, rules: RulesConfig):
        """
        初始化 DiscoveryService

        Args:
            spider: Amazon BSR 爬虫实例
            rules: 过滤规则配置
        """
        self.spider = spider
        self.rules = rules

    async def discover(
        self,
        task: ScanTask,
        bsr_url: Optional[str] = None,
    ) -> List[AmazonProduct]:
        """
        发现 Amazon 产品

        Args:
            task: 扫描任务
            bsr_url: 可选的 BSR 页面 URL（用于自定义类目）

        Returns:
            发现的 Amazon 产品列表
        """
        # 调用爬虫爬取产品
        products = await self.spider.scrape(
            category=task.category,
            max_products=task.max_products,
            bsr_url=bsr_url,
        )

        # 根据规则过滤产品
        filtered_products = self.rules.filter_amazon_products(products)

        # 更新任务产品列表
        for product in filtered_products:
            task.products.append(
                DiscoveredProduct(product=product, status=ProductStatus.PENDING)
            )

        return filtered_products

    async def enrich_products(self, products: List[AmazonProduct]) -> List[AmazonProduct]:
        """
        丰富产品信息（详情页爬取）

        Args:
            products: 基础产品列表

        Returns:
            丰富信息后的产品列表
        """
        return await self.spider.enrich_products(products)

    def filter_products(self, products: List[AmazonProduct]) -> List[AmazonProduct]:
        """
        根据规则过滤产品（不调用爬虫）

        Args:
            products: 产品列表

        Returns:
            过滤后的产品列表
        """
        return self.rules.filter_amazon_products(products)
