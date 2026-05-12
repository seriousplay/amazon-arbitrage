"""
ReviewWorkflow - 人工审核工作流

职责：
- 管理待审核产品队列
- 提供产品批准/拒绝 API
- 返回已批准的产品列表供匹配
"""

from typing import Dict, List, Optional

from app.models.product import AmazonProduct
from app.core.scanner import ScanTask, DiscoveredProduct, ProductStatus


class ReviewWorkflow:
    """人工审核工作流"""

    def __init__(self):
        self._pending_reviews: Dict[str, List[DiscoveredProduct]] = {}
        self._review_results: Dict[str, Dict[str, ProductStatus]] = {}

    def submit_for_review(self, task_id: str, products: List[DiscoveredProduct]) -> str:
        """
        提交产品列表进入审核流程

        Args:
            task_id: 任务ID
            products: 待审核产品列表

        Returns:
            审核批次ID
        """
        batch_id = f"batch_{task_id}_{len(self._pending_reviews.get(task_id, []))}"
        self._pending_reviews[task_id] = products
        self._review_results[task_id] = {}
        return batch_id

    def approve_product(self, task_id: str, asin: str) -> bool:
        """
        批准单个产品

        Args:
            task_id: 任务ID
            asin: Amazon ASIN

        Returns:
            True 如果成功批准，False 如果产品不存在
        """
        if task_id not in self._pending_reviews:
            return False

        for product in self._pending_reviews[task_id]:
            if product.product.asin == asin:
                product.status = ProductStatus.APPROVED
                self._review_results[task_id][asin] = ProductStatus.APPROVED
                return True

        return False

    def reject_product(self, task_id: str, asin: str, reason: str = "") -> bool:
        """
        拒绝单个产品

        Args:
            task_id: 任务ID
            asin: Amazon ASIN
            reason: 拒绝原因

        Returns:
            True 如果成功拒绝，False 如果产品不存在
        """
        if task_id not in self._pending_reviews:
            return False

        for product in self._pending_reviews[task_id]:
            if product.product.asin == asin:
                product.status = ProductStatus.REJECTED
                self._review_results[task_id][asin] = ProductStatus.REJECTED
                return True

        return False

    def get_approved(self, task_id: str) -> List[AmazonProduct]:
        """
        获取已批准的产品列表

        Args:
            task_id: 任务ID

        Returns:
            已批准的 AmazonProduct 列表
        """
        if task_id not in self._pending_reviews:
            return []

        return [
            p.product
            for p in self._pending_reviews[task_id]
            if p.status == ProductStatus.APPROVED
        ]

    def get_pending(self, task_id: str) -> List[DiscoveredProduct]:
        """
        获取待审核产品列表

        Args:
            task_id: 任务ID

        Returns:
            待审核的 DiscoveredProduct 列表
        """
        if task_id not in self._pending_reviews:
            return []

        return [
            p
            for p in self._pending_reviews[task_id]
            if p.status == ProductStatus.PENDING
        ]

    def get_review_summary(self, task_id: str) -> Optional[dict]:
        """
        获取审核摘要

        Args:
            task_id: 任务ID

        Returns:
            审核摘要字典，如果任务不存在则返回 None
        """
        if task_id not in self._pending_reviews:
            return None

        products = self._pending_reviews[task_id]
        results = self._review_results.get(task_id, {})

        return {
            "total": len(products),
            "pending": sum(1 for p in products if p.status == ProductStatus.PENDING),
            "approved": sum(1 for p in products if p.status == ProductStatus.APPROVED),
            "rejected": sum(1 for p in products if p.status == ProductStatus.REJECTED),
            "approval_rate": (
                sum(1 for p in products if p.status == ProductStatus.APPROVED)
                / len(products)
                if products
                else 0.0
            ),
        }

    def clear_task(self, task_id: str) -> None:
        """清理任务的审核数据"""
        self._pending_reviews.pop(task_id, None)
        self._review_results.pop(task_id, None)
