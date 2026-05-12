"""
扫描引擎模块
提供重构后的扫描工作流组件

架构：
- engine.py: ScanOrchestrator - 工作流协调器
- task.py: TaskManager - 任务状态管理
- discovery.py: DiscoveryService - Amazon 产品发现
- matching.py: MatchingService - 1688 匹配
- review.py: ReviewWorkflow - 人工审核流程
- analysis.py: AnalysisService - 市场分析
- models.py: 遗留类型定义（ScanTask, DiscoveredProduct, ProductStatus, Phase）

向后兼容：
- ScanEngine: ScanOrchestrator 的旧名称 facade，提供旧版 API
- ScanTask, DiscoveredProduct, ProductStatus, Phase: 从 models.py 导入的遗留类型
"""

from .engine import ScanOrchestrator
from .task import TaskManager
from .discovery import DiscoveryService
from .matching import MatchingService
from .review import ReviewWorkflow
from .analysis import AnalysisService
from .models import ScanTask, DiscoveredProduct, ProductStatus, Phase

__all__ = [
    "ScanOrchestrator",
    "ScanEngine",  # Backward compatibility alias
    "ScanTask",  # Legacy dataclass
    "DiscoveredProduct",  # Legacy dataclass
    "ProductStatus",  # Legacy enum
    "Phase",  # Legacy enum
    "TaskManager",
    "DiscoveryService",
    "MatchingService",
    "ReviewWorkflow",
    "AnalysisService",
]


# ═══════════════════════════════════════════════════════
# ScanEngine Facade（向后兼容）
# ═══════════════════════════════════════════════════════


class ScanEngine:
    """
    ScanEngine - 向后兼容的 Facade

    将旧版 ScanEngine API 映射到新的 ScanOrchestrator + Services 架构。
    """

    def __init__(self, storage, config):
        self._storage = storage
        self._config = config
        self._orchestrator: Optional[ScanOrchestrator] = None
        self._tasks = {}  # 旧版任务存储，向后兼容

    def _ensure_orchestrator(self):
        if self._orchestrator is None:
            from app.core.scorer import MatchScorer
            from app.core.alibaba_matcher import AlibabaMatcher
            from app.core.amazon_spider import AmazonBSRSpider
            from app.core.rules import RulesConfig
            from app.core.breakout_scorer import BreakoutScorer
            from app.core.concentration import MarketConcentrationAnalyzer
            from app.core.newproduct import NewProductAnalyzer
            from app.core.review_crawler import ReviewCrawler
            from app.core.review_analyzer import ReviewAnalyzer
            from app.core.trends import TrendEngine

            task_manager = TaskManager()
            discovery = DiscoveryService(
                spider=AmazonBSRSpider(self._config),
                rules=RulesConfig.load(),
            )
            matching = MatchingService(
                matcher=AlibabaMatcher(self._config),
                scorer=MatchScorer(self._config),
                config=self._config,
            )
            review = ReviewWorkflow()
            analysis = AnalysisService(config=self._config)

            self._orchestrator = ScanOrchestrator(
                task_manager=task_manager,
                discovery=discovery,
                matching=matching,
                review=review,
                analysis=analysis,
                storage=self._storage,
            )

    @property
    def rules(self):
        from app.core.rules import RulesConfig

        return RulesConfig.load()

    @property
    def storage(self):
        return self._storage

    @property
    def config(self):
        return self._config

    @property
    def alibaba_matcher(self):
        """访问内部 AlibabaMatcher（兼容旧版测试）"""
        self._ensure_orchestrator()
        return self._orchestrator.matching.matcher if self._orchestrator else None

    @property
    def amazon_spider(self):
        """访问内部 AmazonBSRSpider（兼容旧版测试）"""
        self._ensure_orchestrator()
        return self._orchestrator.discovery.spider if self._orchestrator else None

    async def start_quick_scan(self, category, max_products=10, bsr_url=None, callback=None):
        self._ensure_orchestrator()
        task_id = await self._orchestrator.start_quick_scan(
            category=category,
            max_products=max_products,
        )
        task = self._orchestrator.tasks.get_task(task_id)
        if task:
            self._tasks[task_id] = task
        return task_id

    async def start_discover_only(self, category, max_products=15, bsr_url=None, callback=None):
        self._ensure_orchestrator()
        task_id = await self._orchestrator.start_discover_only(
            category=category,
            max_products=max_products,
            bsr_url=bsr_url,
        )
        task = self._orchestrator.tasks.get_task(task_id)
        if task:
            self._tasks[task_id] = task
        return task_id

    async def start_discover(self, category, max_products=10, bsr_url=None, callback=None):
        return await self.start_discover_only(category, max_products, bsr_url, callback)

    async def start_match_only(self, task_id, callback=None):
        self._ensure_orchestrator()
        task = self._orchestrator.tasks.get_task(task_id)
        if not task:
            return False
        return await self._orchestrator.resume_task(task_id)

    async def start_matching(self, task_id, callback=None):
        return await self.start_match_only(task_id, callback)

    def approve_product(self, task_id, asin):
        return (
            self._orchestrator.review.approve_product(task_id, asin)
            if self._orchestrator
            else False
        )

    def reject_product(self, task_id, asin):
        return (
            self._orchestrator.review.reject_product(task_id, asin) if self._orchestrator else False
        )

    def approve_all_products(self, task_id):
        if self._orchestrator:
            task = self._orchestrator.tasks.get_task(task_id)
            if task:
                task.approve_all()
                return task.approved_count
        return 0

    def get_task(self, task_id):
        if self._orchestrator:
            task = self._orchestrator.tasks.get_task(task_id)
            if task:
                return task
        return self._tasks.get(task_id)

    def list_tasks(self):
        if self._orchestrator:
            return self._orchestrator.tasks.get_all_tasks()
        return list(self._tasks.values())

    async def start_scan(self, **kwargs):
        category = kwargs.get("category", "Pet Supplies")
        max_products = kwargs.get("max_products", 10)
        bsr_url = kwargs.get("bsr_url")
        return await self.start_quick_scan(category, max_products, bsr_url)

    async def test_1688_search(self, keyword):
        self._ensure_orchestrator()
        from app.core.alibaba_matcher import AlibabaMatcher

        matcher = AlibabaMatcher(self._config)
        results = await matcher.search_and_match(keyword)
        return [r.model_dump() for r in results] if results else []

    def get_review_analysis(self, task_id):
        return None

    def list_trends(self):
        return []

    def get_trend(self, keyword):
        return None

    def refresh_trends(self):
        return {"success": False, "message": "Not implemented in new architecture"}

    async def update_trend_from_web(self, keyword):
        return {"success": False, "message": "Not implemented in new architecture"}

    async def _match_parallel(self, task, products, callback) -> List[MatchResult]:
        """
        并行匹配 Amazon 商品到 1688 供应商（兼容旧版测试）

        Args:
            task: ScanTask
            products: Amazon 产品列表
            callback: 进度回调

        Returns:
            MatchResult 列表
        """
        self._ensure_orchestrator()
        return await self._orchestrator.matching.match_products(task, products)

    async def cancel_all(self):
        self._ensure_orchestrator()
        count = 0
        for task_id in list(self._orchestrator._running_tasks.keys()):
            if await self._orchestrator.cancel_task(task_id):
                count += 1
        return count

    async def cleanup(self):
        if self._orchestrator:
            pass
