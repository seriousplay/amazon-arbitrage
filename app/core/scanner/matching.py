"""
MatchingService - 1688 匹配服务

职责：
- 为 Amazon 产品在 1688 上查找同款商品
- 管理匹配并发控制
- 计算匹配分数
- 返回 MatchResult 列表
"""

import asyncio
from typing import List, Optional

from app.models.product import AmazonProduct, AlibabaProduct, MatchResult
from app.core.scorer import MatchScorer
from app.core.alibaba_matcher import AlibabaMatcher
from app.config import settings


# 延迟导入以避免循环依赖
def _get_scanner_types():
    """从旧 scanner 模块获取类型（延迟导入）"""
    from app.core.scanner import ScanTask, DiscoveredProduct, ProductStatus

    return ScanTask, DiscoveredProduct, ProductStatus


class MatchingService:
    """1688 商品匹配服务"""

    def __init__(
        self,
        matcher: AlibabaMatcher,
        scorer: MatchScorer,
        config=settings,
    ):
        """
        初始化 MatchingService

        Args:
            matcher: 1688 匹配器
            scorer: 匹配分数计算器
            config: 配置对象
        """
        self.matcher = matcher
        self.scorer = scorer
        self.config = config
        self._semaphore = asyncio.Semaphore(getattr(config, "DEFAULT_MATCH_CONCURRENCY", 3))

    async def match_products(
        self,
        task,  # 使用延迟导入的类型，见 _get_scanner_types()
        products: List[AmazonProduct],
    ) -> List[MatchResult]:
        """
        为多个 Amazon 产品匹配 1688 商品

        Args:
            task: 扫描任务
            products: 要匹配的 Amazon 产品列表

        Returns:
            匹配结果列表
        """
        # 延迟导入类型
        ScanTask, DiscoveredProduct, ProductStatus = _get_scanner_types()

        results = []

        # 并发匹配（受信号量控制）
        async def match_single(product: AmazonProduct) -> Optional[MatchResult]:
            async with self._semaphore:
                try:
                    # 调用 AlibabaMatcher 查找匹配商品
                    alibaba_product = await self.matcher.search_and_match(
                        title=product.title,
                        category=product.category,
                    )

                    if alibaba_product is None:
                        return None

                    # 计算匹配分数
                    match_result = self.scorer.score_match(
                        amazon=product,
                        alibaba=alibaba_product,
                    )

                    return match_result

                except Exception as e:
                    # 记录错误但不中断整个批次
                    import logging

                    logging.getLogger(__name__).error(f"匹配失败 {product.asin}: {e}")
                    return None

        # 并发执行所有匹配任务
        tasks = [match_single(p) for p in products]
        matched_results = await asyncio.gather(*tasks, return_exceptions=False)

        # 过滤掉 None 结果
        results = [r for r in matched_results if r is not None]

        # 更新任务状态
        for product, result in zip(products, matched_results):
            if result:
                # 更新产品状态为已匹配
                for discovered in task.products:
                    if discovered.product.asin == product.asin:
                        discovered.status = ProductStatus.MATCHED
                        discovered.match_result = result
                        break
            else:
                # 标记为匹配失败
                for discovered in task.products:
                    if discovered.product.asin == product.asin:
                        discovered.status = ProductStatus.REJECTED
                        break

        return results

    async def match_single_product(
        self,
        product: AmazonProduct,
    ) -> Optional[MatchResult]:
        """
        为单个 Amazon 产品匹配 1688 商品

        Args:
            product: Amazon 产品

        Returns:
            匹配结果，如果没有找到则返回 None
        """
        async with self._semaphore:
            try:
                alibaba_product = await self.matcher.search_and_match(
                    title=product.title,
                    category=product.category,
                )

                if alibaba_product is None:
                    return None

                return self.scorer.score_match(
                    amazon=product,
                    alibaba=alibaba_product,
                )

            except Exception as e:
                import logging

                logging.getLogger(__name__).error(f"匹配失败 {product.asin}: {e}")
                return None
