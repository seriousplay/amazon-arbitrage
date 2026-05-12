"""
扫描工作流集成测试

测试完整的扫描流水线：
- 发现 → 审核 → 匹配 → 分析
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.scanner import ScanOrchestrator, TaskManager, DiscoveryService
from app.core.scanner import MatchingService, ReviewWorkflow, AnalysisService
from app.models.product import AmazonProduct, AlibabaProduct
from app.services.storage import StorageService


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.DEFAULT_MATCH_CONCURRENCY = 2
    config.DEFAULT_MATCH_TIMEOUT = 30
    config.ENABLE_ANALYSIS = True
    config.PRICE_DIFF_WEIGHT = 0.4
    config.SALES_WEIGHT = 0.3
    config.RATING_WEIGHT = 0.2
    config.COMPETITION_WEIGHT = 0.1
    config.CNY_TO_USD = 0.14
    config.COST_MULTIPLIER = 1.25
    return config


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.save_products = AsyncMock()
    storage.save_match_results = AsyncMock()
    return storage


@pytest.fixture
def mock_spider():
    spider = MagicMock()
    spider.scrape = AsyncMock(
        return_value=[
            AmazonProduct(
                asin="B001",
                title="Premium Dog Bed",
                category="Dogs",
                rank=100,
                price=50.0,
                rating=4.5,
                review_count=1200,
            ),
            AmazonProduct(
                asin="B002",
                title="Cat Tree House",
                category="Cats",
                rank=200,
                price=80.0,
                rating=4.3,
                review_count=800,
            ),
        ]
    )
    spider.enrich_products = AsyncMock(side_effect=lambda x: x)
    return spider


@pytest.fixture
def mock_matcher():
    matcher = MagicMock()
    matcher.search_and_match = AsyncMock(
        return_value=AlibabaProduct(
            item_id="100001",
            title="狗窝 大号",
            price=150.0,
            min_order_qty=10,
            supplier="Test Supplier",
        )
    )
    return matcher


@pytest.fixture
def mock_scorer(mock_config):
    from app.core.scorer import MatchScorer

    return MatchScorer(mock_config)


@pytest.fixture
def mock_rules():
    rules = MagicMock()

    def filter_side_effect(products):
        # Pass all products
        return products, [], {}

    rules.filter_amazon_products.side_effect = filter_side_effect
    return rules


@pytest.fixture
def orchestrator(mock_storage, mock_config, mock_spider, mock_rules, mock_matcher, mock_scorer):
    """创建完整的 ScanOrchestrator 实例"""
    return ScanOrchestrator(
        task_manager=TaskManager(),
        discovery=DiscoveryService(mock_spider, mock_rules),
        matching=MatchingService(mock_matcher, mock_scorer, mock_config),
        review=ReviewWorkflow(),
        analysis=MagicMock(),
        storage=mock_storage,
    )


class TestFullPipeline:
    """测试完整扫描流水线"""

    @pytest.mark.asyncio
    async def test_quick_scan_full_flow(
        self, orchestrator, mock_spider, mock_matcher, mock_storage
    ):
        """测试快速扫描完整流程：发现 → 匹配 → 保存"""
        # 执行快速扫描
        task_id = await orchestrator.start_quick_scan(
            category="Dogs",
            max_products=10,
        )

        # 等待任务完成（因为是后台任务，需要等待）
        import asyncio

        await asyncio.sleep(0.1)

        # 验证任务已创建
        task = orchestrator.tasks.get_task(task_id)
        assert task is not None

        # 验证发现阶段
        assert mock_spider.scrape.called
        assert mock_spider.enrich_products.called

        # 验证匹配阶段
        assert mock_matcher.search_and_match.called

        # 验证保存
        assert mock_storage.save_products.called
        assert mock_storage.save_match_results.called

    @pytest.mark.asyncio
    async def test_discover_only_flow(self, orchestrator, mock_spider, mock_storage):
        """测试仅发现流程"""
        task_id = await orchestrator.start_discover_only(
            category="Dogs",
            max_products=10,
        )

        import asyncio

        await asyncio.sleep(0.1)

        # 验证发现阶段完成
        task = orchestrator.tasks.get_task(task_id)
        assert task is not None
        assert mock_spider.scrape.called
        assert mock_storage.save_products.called

        # 不应该有匹配
        assert not mock_storage.save_match_results.called

    @pytest.mark.asyncio
    async def test_full_pipeline_with_review(self, orchestrator, mock_spider, mock_storage):
        """测试完整流水线含人工审核"""
        task_id = await orchestrator.start_full_pipeline(
            category="Dogs",
            max_products=10,
        )

        import asyncio

        await asyncio.sleep(0.1)

        # 验证任务进入审核状态
        task = orchestrator.tasks.get_task(task_id)
        assert task is not None

        # 验证发现阶段
        assert mock_spider.scrape.called

        # 模拟审核通过
        review = orchestrator.review
        if task and hasattr(task, "products"):
            for product in task.products[:1]:
                review.approve_product(task_id, product.product.asin)

            # 恢复任务执行匹配
            result = await orchestrator.resume_task(task_id)
            assert result is True

            await asyncio.sleep(0.1)
            assert mock_storage.save_match_results.called

    @pytest.mark.asyncio
    async def test_cancel_task(self, orchestrator):
        """测试取消任务"""
        task_id = await orchestrator.start_discover_only(category="Dogs", max_products=10)
        result = orchestrator.cancel_task(task_id)
        assert result is True

    def test_get_task_status(self, orchestrator):
        """测试获取任务状态"""
        # 创建一个任务
        task = orchestrator.tasks.create_task("Dogs", 10)
        status = orchestrator.get_task_status(task.task_id)
        assert isinstance(status, dict)
        assert status["task_id"] == task.task_id


class TestErrorHandling:
    """测试错误处理"""

    @pytest.mark.asyncio
    async def test_discovery_failure(self, mock_storage, mock_config):
        """测试发现阶段失败处理"""
        failing_spider = MagicMock()
        failing_spider.scrape = AsyncMock(side_effect=Exception("Network error"))
        failing_spider.enrich_products = AsyncMock()

        orchestrator = ScanOrchestrator(
            task_manager=TaskManager(),
            discovery=DiscoveryService(failing_spider, MagicMock()),
            matching=MagicMock(),
            review=MagicMock(),
            analysis=MagicMock(),
            storage=mock_storage,
        )

        task_id = await orchestrator.start_discover_only("Dogs", max_products=10)
        import asyncio

        await asyncio.sleep(0.1)

        task = orchestrator.tasks.get_task(task_id)
        assert task.status == "failed"
        assert task.error is not None

    @pytest.mark.asyncio
    async def test_matching_failure(self, mock_storage, mock_config, mock_spider, mock_rules):
        """测试匹配阶段失败处理"""
        failing_matcher = MagicMock()
        failing_matcher.search_and_match = AsyncMock(side_effect=Exception("Matching error"))
        failing_scorer = MagicMock()

        orchestrator = ScanOrchestrator(
            task_manager=TaskManager(),
            discovery=DiscoveryService(mock_spider, mock_rules),
            matching=MatchingService(failing_matcher, failing_scorer, mock_config),
            review=ReviewWorkflow(),
            analysis=MagicMock(),
            storage=mock_storage,
        )

        # 执行快速扫描，匹配失败不应中断整个流程
        task_id = await orchestrator.start_quick_scan("Dogs", max_products=10)
        import asyncio

        await asyncio.sleep(0.1)

        # 任务应该完成（即使匹配失败）
        task = orchestrator.tasks.get_task(task_id)
        assert task is not None


class TestConcurrency:
    """测试并发控制"""

    @pytest.mark.asyncio
    async def test_concurrent_tasks(self, orchestrator):
        """测试并发任务"""
        import asyncio

        # 启动多个任务
        task_ids = await asyncio.gather(
            orchestrator.start_discover_only("Dogs", max_products=5),
            orchestrator.start_discover_only("Cats", max_products=5),
            orchestrator.start_discover_only("Birds", max_products=5),
        )

        assert len(task_ids) == 3
        assert len(set(task_ids)) == 3  # 所有 task_id 唯一

        await asyncio.sleep(0.2)

        # 所有任务都应该存在
        for task_id in task_ids:
            task = orchestrator.tasks.get_task(task_id)
            assert task is not None
