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
from typing import TYPE_CHECKING, List, Optional

from app.models.product import AmazonProduct, MatchResult
from app.core.scanner.task import TaskManager
from app.core.scanner.discovery import DiscoveryService
from app.core.scanner.matching import MatchingService
from app.core.scanner.review import ReviewWorkflow
from app.core.scanner.analysis import AnalysisService
from app.core.scanner.models import Phase, ProductStatus
from app.services.storage import StorageService
from app.config import settings

if TYPE_CHECKING:
    from app.core.scanner import ScanTask


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
                task.phase = Phase.DISCOVER

                # 1. 发现产品（含规则过滤）
                products = await self.discovery.discover(task, bsr_url=bsr_url)

                # 2. 丰富产品信息
                if products:
                    products = await self.discovery.enrich_products(products)

                # 3. 保存到数据库
                if products:
                    await self.storage.save_products(task_id, products)

                # 4. 生成爆款初评（关键：使用 breakout_scorer 评分）
                if products:
                    task.current_step = "📈 生成爆款初评..."
                    task.progress = 0.8
                    # 注意：此时还没有 1688 匹配数据，所以传入空 dict
                    breakout = self.analysis.breakout_scorer.score_batch(products, {})
                    task.breakout_results = breakout

                    # 将所有产品标记为已批准（用于后续 1688 匹配）
                    from app.core.scanner.models import ProductStatus
                    for p in task.products:
                        if p.status == ProductStatus.PENDING:
                            p.status = ProductStatus.APPROVED
                    task.amazon_count = len(products)

                    # 更新完成状态
                    task.current_step = f"✅ 发现 {len(products)} 个潜在商品（规则过滤后），可进行1688匹配"

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
                task.phase = Phase.DISCOVER

                # 1. 发现产品
                products = await self.discovery.discover(task)

                if not products:
                    task.status = "completed"
                    task.progress = 100.0
                    task.completed_at = datetime.now()
                    return

                # 2. 丰富产品信息
                products = await self.discovery.enrich_products(products)

                # 3. 保存产品到数据库
                await self.storage.save_products(task_id, products)
                task.amazon_count = len(products)

                # 4. 自动批准或进入人工审核
                if auto_approve:
                    task.approve_all()
                else:
                    # 进入人工审核流程
                    batch_id = self.review.submit_for_review(task_id, task.products)
                    task.status = "awaiting_review"
                    task.current_step = f" awaiting_review_batch_{batch_id}"
                    return

                # 5. 匹配 1688
                task.phase = Phase.MATCHING
                task.status = "running"
                task.current_step = "matching_products"

                approved_products = task.get_approved_products()
                match_results = await self.matching.match_products(task, approved_products)

                # 6. 保存匹配结果
                if match_results:
                    await self.storage.save_match_results(task_id, match_results)

                # 7. 生成爆款评分（含1688利润数据）
                task.current_step = "📈 生成爆款评分..."
                task.progress = 0.9
                match_map = {r.amazon.asin: r for r in match_results} if match_results else {}
                breakout = self.analysis.breakout_scorer.score_batch(approved_products, match_map)
                task.breakout_results = breakout

                task.status = "completed"
                task.progress = 100.0
                task.current_step = f"✅ 快速扫描完成：发现 {len(approved_products)} 个产品，匹配 {len(match_results)} 个货源"
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
                task.phase = Phase.DISCOVER
                task.current_step = "discovering_products"
                products = await self.discovery.discover(task)

                if not products:
                    task.status = "completed"
                    task.progress = 100.0
                    task.completed_at = datetime.now()
                    return

                # 2. 丰富产品信息
                products = await self.discovery.enrich_products(products)

                # 3. 生成爆款初评（进入审核前的初步评分）
                task.current_step = "📈 生成爆款初评..."
                task.progress = 0.8
                breakout = self.analysis.breakout_scorer.score_batch(products, {})
                task.breakout_results = breakout
                task.amazon_count = len(products)

                # 4. 进入人工审核
                task.phase = Phase.REVIEW
                batch_id = self.review.submit_for_review(task_id, task.products)
                task.status = "awaiting_review"
                task.current_step = f"⏳ 等待审核（批次 {batch_id}）"

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
                task.phase = Phase.MATCHING
                task.status = "running"
                task.current_step = "matching_products"

                match_results = await self.matching.match_products(task, approved_products)

                if match_results:
                    await self.storage.save_match_results(task_id, match_results)

                # 生成爆款评分（含1688利润数据）
                task.current_step = "📈 生成爆款评分..."
                task.progress = 0.9
                match_map = {r.amazon.asin: r for r in match_results} if match_results else {}
                breakout = self.analysis.breakout_scorer.score_batch(approved_products, match_map)
                task.breakout_results = breakout

                task.status = "completed"
                task.progress = 100.0
                task.current_step = f"✅ 全流程完成：审核 {len(approved_products)} 个产品，匹配 {len(match_results)} 个货源"
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
