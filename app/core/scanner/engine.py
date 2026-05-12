"""
ScanOrchestrator - 扫描工作流协调器

职责：
- 协调三阶段扫描工作流（发现 → 审核 → 匹配）
- 委托各 Service 执行具体任务
- 提供简化的 API 供外部调用
- 支持快速扫描、仅发现、完整流水线等模式
"""

import asyncio
from datetime import datetime
from typing import List, Optional

from app.models.product import AmazonProduct, MatchResult
from app.core.scanner import ScanTask
from app.core.scanner.task import TaskManager
from app.core.scanner.discovery import DiscoveryService
from app.core.scanner.matching import MatchingService
from app.core.scanner.review import ReviewWorkflow
from app.core.scanner.analysis import AnalysisService
from app.services.storage import StorageService
from app.config import settings


class ScanOrchestrator:
    """
    扫描工作流协调器

    使用组合模式而非继承，通过注入各个 Service 来协调工作流。
    这与原 ScanEngine 不同，职责更清晰，更易于测试。
    """

    def __init__(
        self,
        task_manager: TaskManager,
        discovery: DiscoveryService,
        matching: MatchingService,
        review: ReviewWorkflow,
        analysis: AnalysisService,
        storage: StorageService,
    ):
        """
        初始化 ScanOrchestrator

        Args:
            task_manager: 任务管理器
            discovery: 产品发现服务
            matching: 匹配服务
            review: 审核工作流
            analysis: 分析服务
            storage: 存储服务
        """
        self.tasks = task_manager
        self.discovery = discovery
        self.matching = matching
        self.review = review
        self.analysis = analysis
        self.storage = storage
        self._running_tasks: dict = {}
        self._lock = asyncio.Lock()

    async def start_discover_only(
        self,
        category: str,
        max_products: int = 10,
        bsr_url: Optional[str] = None,
    ) -> str:
        """
        仅执行发现阶段（不匹配 1688）

        Args:
            category: 产品类目
            max_products: 最大发现产品数
            bsr_url: 可选的 BSR URL

        Returns:
            任务ID
        """
        # 创建任务
        task = self.tasks.create_task(category, max_products)
        task_id = task.task_id

        # 后台执行发现
        async def run_discovery():
            try:
                task.status = "running"
                task.phase = "discover"

                # 1. 发现产品
                products = await self.discovery.discover(task, bsr_url=bsr_url)

                # 2. 丰富产品信息
                if products:
                    products = await self.discovery.enrich_products(products)

                # 3. 保存到数据库
                if products:
                    await self.storage.save_products(task_id, products)

                task.status = "completed"
                task.progress = 100.0
                task.completed_at = datetime.now()

            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                task.completed_at = datetime.now()

        # 启动后台任务
        asyncio_task = asyncio.create_task(run_discovery())
        self._running_tasks[task_id] = asyncio_task

        return task_id

    async def start_quick_scan(
        self,
        category: str,
        max_products: int = 10,
        auto_approve: bool = True,
    ) -> str:
        """
        快速扫描（发现 → 自动批准 → 匹配）

        Args:
            category: 产品类目
            max_products: 最大发现产品数
            auto_approve: 是否自动批准所有产品

        Returns:
            任务ID
        """
        task = self.tasks.create_task(category, max_products)
        task_id = task.task_id

        async def run_quick_scan():
            try:
                task.status = "running"
                task.phase = "discover"

                # 1. 发现产品
                products = await self.discovery.discover(task)

                if not products:
                    task.status = "completed"
                    task.progress = 100.0
                    task.completed_at = datetime.now()
                    return

                # 2. 丰富产品信息
                products = await self.discovery.enrich_products(products)

                # 3. 自动批准或进入人工审核
                if auto_approve:
                    task.approve_all()
                else:
                    # 进入人工审核流程
                    batch_id = self.review.submit_for_review(
                        task_id, task.products
                    )
                    task.status = "awaiting_review"
                    task.current_step = f" awaiting_review_batch_{batch_id}"
                    return

                # 4. 匹配 1688
                task.phase = "match"
                task.status = "running"
                task.current_step = "matching_products"

                approved_products = task.get_approved_products()
                match_results = await self.matching.match_products(
                    task, approved_products
                )

                # 5. 保存结果
                if match_results:
                    await self.storage.save_match_results(task_id, match_results)

                task.status = "completed"
                task.progress = 100.0
                task.completed_at = datetime.now()

            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                task.completed_at = datetime.now()

        asyncio_task = asyncio.create_task(run_quick_scan())
        self._running_tasks[task_id] = asyncio_task

        return task_id

    async def start_full_pipeline(
        self,
        category: str,
        max_products: int = 10,
    ) -> str:
        """
        完整流水线（发现 → 审核 → 匹配 → 分析）

        Args:
            category: 产品类目
            max_products: 最大发现产品数

        Returns:
            任务ID
        """
        task = self.tasks.create_task(category, max_products)
        task_id = task.task_id

        async def run_full_pipeline():
            try:
                task.status = "running"

                # 1. 发现阶段
                task.phase = "discover"
                task.current_step = "discovering_products"
                products = await self.discovery.discover(task)

                if not products:
                    task.status = "completed"
                    task.progress = 100.0
                    task.completed_at = datetime.now()
                    return

                # 2. 丰富产品信息
                products = await self.discovery.enrich_products(products)

                # 3. 进入人工审核
                task.phase = "review"
                batch_id = self.review.submit_for_review(task_id, task.products)
                task.status = "awaiting_review"
                task.current_step = f"review_batch_{batch_id}"

                # 注意：完整流水线在此暂停，等待人工审核完成
                # 审核完成后，需要调用 resume_task() 继续执行

            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                task.completed_at = datetime.now()

        asyncio_task = asyncio.create_task(run_full_pipeline())
        self._running_tasks[task_id] = asyncio_task

        return task_id

    async def resume_task(self, task_id: str) -> bool:
        """
        恢复暂停的任务（如完成人工审核后继续匹配）

        Args:
            task_id: 任务ID

        Returns:
            True 如果成功恢复，False 如果任务不存在或状态不正确
        """
        task = self.tasks.get_task(task_id)
        if task is None or task.status != "awaiting_review":
            return False

        # 获取已批准的产品
        approved_products = self.review.get_approved(task_id)

        if not approved_products:
            task.status = "completed"
            task.completed_at = datetime.now()
            return True

        # 继续执行匹配
        async def continue_matching():
            try:
                task.phase = "match"
                task.status = "running"
                task.current_step = "matching_products"

                match_results = await self.matching.match_products(
                    task, approved_products
                )

                if match_results:
                    await self.storage.save_match_results(task_id, match_results)

                # 可选：执行市场分析
                if getattr(self.config, 'ENABLE_ANALYSIS', True):
                    task.phase = "analysis"
                    task.current_step = "analyzing_market"

                    await self.analysis.analyze_breakout(approved_products)
                    await self.analysis.analyze_concentration(approved_products)
                    # ... 其他分析

                task.status = "completed"
                task.progress = 100.0
                task.completed_at = datetime.now()

            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                task.completed_at = datetime.now()

        asyncio_task = asyncio.create_task(continue_matching())
        self._running_tasks[task_id] = asyncio_task

        return True

    def cancel_task(self, task_id: str) -> bool:
        """
        取消正在运行的任务

        Args:
            task_id: 任务ID

        Returns:
            True 如果成功取消
        """
        # 取消 asyncio 任务
        if task_id in self._running_tasks:
            asyncio_task = self._running_tasks[task_id]
            if not asyncio_task.done():
                asyncio_task.cancel()
            del self._running_tasks[task_id]

        # 更新任务状态
        return self.tasks.cancel_task(task_id)

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """
        获取任务状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态字典
        """
        return self.tasks.get_task_summary(task_id)
