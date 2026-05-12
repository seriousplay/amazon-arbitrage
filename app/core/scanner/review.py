"""
ReviewWorkflow - 人工审核工作流

职责：
- 管理待审核产品队列
- 提供产品批准/拒绝 API
- 返回已批准的产品列表供匹配
"""

from typing import Dict, List, Optional

from app.models.product import AmazonProduct


class ReviewWorkflow:
    """人工审核工作流"""

    def __init__(self):
        # task_id -> list of AmazonProduct
        self._pending_reviews: Dict[str, List[AmazonProduct]] = {}
        self._review_results: Dict[str, Dict[str, str]] = {}  # asin -> "approved"/"rejected"

    def submit_for_review(self, task_id: str, products: List[AmazonProduct]) -> str:
        """
        提交产品列表进入审核流程

        Args:
            task_id: 任务ID
            products: 待审核产品列表（可以是 AmazonProduct 或 DiscoveredProduct）

        Returns:
            审核批次ID
        """
        # 兼容 DiscoveredProduct 对象
        normalized = []
        for p in products:
            if hasattr(p, "product"):
                # DiscoveredProduct 对象，提取内部的 AmazonProduct
                normalized.append(p.product)
            else:
                normalized.append(p)

        batch_id = f"batch_{task_id}_{len(self._pending_reviews.get(task_id, []))}"
        self._pending_reviews[task_id] = normalized
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
            if product.asin == asin:
                self._review_results[task_id][asin] = "approved"
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
            if product.asin == asin:
                self._review_results[task_id][asin] = "rejected"
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
        if task_id not in self._review_results:
            return []

        approved_asins = {
            asin for asin, status in self._review_results[task_id].items() if status == "approved"
        }

        return [p for p in self._pending_reviews.get(task_id, []) if p.asin in approved_asins]

    def get_pending(self, task_id: str) -> List[AmazonProduct]:
        """
        获取待审核产品列表

        Args:
            task_id: 任务ID

        Returns:
            待审核的 AmazonProduct 列表
        """
        if task_id not in self._pending_reviews:
            return []

        reviewed_asins = set(self._review_results.get(task_id, {}).keys())
        return [p for p in self._pending_reviews[task_id] if p.asin not in reviewed_asins]

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

        approved = sum(1 for status in results.values() if status == "approved")
        rejected = sum(1 for status in results.values() if status == "rejected")
        pending = len(products) - approved - rejected

        return {
            "total": len(products),
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "approval_rate": approved / len(products) if products else 0.0,
        }

    def clear_task(self, task_id: str) -> None:
        """清理任务的审核数据"""
        self._pending_reviews.pop(task_id, None)
        self._review_results.pop(task_id, None)
