"""
扫描工作流组件测试

测试覆盖：
- TaskManager 任务生命周期
- DiscoveryService 产品发现
- MatchingService 1688 匹配
- ReviewWorkflow 审核流程
- ScanOrchestrator 工作流协调
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.models.product import AmazonProduct, AlibabaProduct, MatchResult
from app.core.scanner import (
    TaskManager,
    DiscoveryService,
    MatchingService,
    ReviewWorkflow,
    ScanOrchestrator,
)
from app.core.scorer import MatchScorer
from app.services.storage import StorageService

# ═══════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════


@pytest.fixture
def task_manager():
    """创建 TaskManager 实例"""
    return TaskManager()


@pytest.fixture
def review_workflow():
    """创建 ReviewWorkflow 实例"""
    return ReviewWorkflow()


@pytest.fixture
def mock_config():
    """创建模拟配置"""
    config = MagicMock()
    config.DEFAULT_MATCH_CONCURRENCY = 3
    config.DEFAULT_MATCH_TIMEOUT = 90
    config.ENABLE_ANALYSIS = True
    config.PRICE_DIFF_WEIGHT = 0.4
    config.SALES_WEIGHT = 0.3
    config.RATING_WEIGHT = 0.2
    config.COMPETITION_WEIGHT = 0.1
    config.CNY_TO_USD = 0.14
    config.COST_MULTIPLIER = 1.25
    return config


@pytest.fixture
def mock_matcher():
    """创建模拟匹配器"""
    matcher = MagicMock()
    matcher.search_and_match = AsyncMock()
    return matcher


@pytest.fixture
def mock_scorer(mock_config):
    """创建真实 MatchScorer"""
    return MatchScorer(mock_config)


@pytest.fixture
def mock_spider():
    """创建模拟爬虫"""
    spider = MagicMock()
    spider.scrape = AsyncMock()
    spider.enrich_products = AsyncMock()
    return spider


@pytest.fixture
def mock_rules():
    """创建模拟规则"""
    rules = MagicMock()
    # filter_amazon_products 返回 (passed, filtered, reasons)
    # 默认通过所有产品（使用 return_value 而非 side_effect，便于测试时覆盖）
    rules.filter_amazon_products.return_value = ([], [], {})
    return rules


@pytest.fixture
def discovery_service(mock_spider, mock_rules):
    """创建 DiscoveryService"""
    return DiscoveryService(spider=mock_spider, rules=mock_rules)


@pytest.fixture
def matching_service(mock_matcher, mock_scorer, mock_config):
    """创建 MatchingService"""
    return MatchingService(
        matcher=mock_matcher,
        scorer=mock_scorer,
        config=mock_config,
    )


@pytest.fixture
def mock_storage():
    """创建模拟存储服务"""
    storage = MagicMock()
    storage.save_products = AsyncMock()
    storage.save_match_results = AsyncMock()
    return storage


@pytest.fixture
def sample_amazon_products():
    """创建示例 Amazon 产品"""
    return [
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


@pytest.fixture
def sample_alibaba_product():
    """创建示例 1688 产品"""
    return AlibabaProduct(
        item_id="100001",
        title="宠物狗窝 大号",
        price=150.0,
        min_order_qty=10,
        supplier="Test Supplier",
    )


# ═══════════════════════════════════════════════════════
# TaskManager Tests
# ═══════════════════════════════════════════════════════


class TestTaskManager:
    """测试任务管理器"""

    def test_create_task(self, task_manager):
        """测试创建任务"""
        task = task_manager.create_task(category="Dogs", max_products=10)
        assert task.task_id is not None
        assert task.category == "Dogs"
        assert task.max_products == 10
        assert task.status == "pending"

    def test_get_task(self, task_manager):
        """测试获取任务"""
        created_task = task_manager.create_task("Dogs", 10)
        retrieved_task = task_manager.get_task(created_task.task_id)
        assert retrieved_task == created_task

    def test_get_nonexistent_task(self, task_manager):
        """测试获取不存在的任务"""
        result = task_manager.get_task("nonexistent_id")
        assert result is None

    def test_get_all_tasks(self, task_manager):
        """测试获取所有任务"""
        task_manager.create_task("Dogs", 10)
        task_manager.create_task("Cats", 15)
        all_tasks = task_manager.get_all_tasks()
        assert len(all_tasks) == 2

    def test_update_task(self, task_manager):
        """测试更新任务"""
        task = task_manager.create_task("Dogs", 10)
        task.status = "running"
        task_manager.update_task(task)
        retrieved = task_manager.get_task(task.task_id)
        assert retrieved.status == "running"

    def test_update_nonexistent_task_raises_error(self, task_manager):
        """测试更新不存在的任务抛出异常"""
        from app.core.scanner.task import ScanTask

        task = ScanTask("fake_id", "Dogs", 10)
        with pytest.raises(KeyError):
            task_manager.update_task(task)

    def test_cancel_task(self, task_manager):
        """测试取消任务"""
        task = task_manager.create_task("Dogs", 10)
        task.status = "running"
        result = task_manager.cancel_task(task.task_id)
        assert result is True
        assert task.status == "cancelled"

    def test_cancel_completed_task_fails(self, task_manager):
        """测试取消已完成任务失败"""
        task = task_manager.create_task("Dogs", 10)
        task.status = "completed"
        result = task_manager.cancel_task(task.task_id)
        assert result is False

    def test_get_task_summary(self, task_manager):
        """测试获取任务摘要"""
        task = task_manager.create_task("Dogs", 10)
        summary = task_manager.get_task_summary(task.task_id)
        assert isinstance(summary, dict)
        assert "task_id" in summary
        assert "category" in summary


# ═══════════════════════════════════════════════════════
# ReviewWorkflow Tests
# ═══════════════════════════════════════════════════════


class TestReviewWorkflow:
    """测试审核工作流"""

    def test_submit_for_review(self, review_workflow, sample_amazon_products):
        """测试提交审核"""
        batch_id = review_workflow.submit_for_review("task_1", sample_amazon_products)
        assert isinstance(batch_id, str)
        assert "task_1" in batch_id

    def test_approve_product(self, review_workflow, sample_amazon_products):
        """测试批准产品"""
        review_workflow.submit_for_review("task_1", sample_amazon_products)
        result = review_workflow.approve_product("task_1", "B001")
        assert result is True

    def test_reject_product(self, review_workflow, sample_amazon_products):
        """测试拒绝产品"""
        review_workflow.submit_for_review("task_1", sample_amazon_products)
        result = review_workflow.reject_product("task_1", "B002", reason="too expensive")
        assert result is True

    def test_get_approved(self, review_workflow, sample_amazon_products):
        """测试获取已批准产品"""
        review_workflow.submit_for_review("task_1", sample_amazon_products)
        review_workflow.approve_product("task_1", "B001")
        review_workflow.reject_product("task_1", "B002")

        approved = review_workflow.get_approved("task_1")
        assert len(approved) == 1
        assert approved[0].asin == "B001"

    def test_get_pending(self, review_workflow, sample_amazon_products):
        """测试获取待审核产品"""
        review_workflow.submit_for_review("task_1", sample_amazon_products)
        review_workflow.approve_product("task_1", "B001")

        pending = review_workflow.get_pending("task_1")
        assert len(pending) == 1
        assert pending[0].asin == "B002"

    def test_get_review_summary(self, review_workflow, sample_amazon_products):
        """测试获取审核摘要"""
        review_workflow.submit_for_review("task_1", sample_amazon_products)
        review_workflow.approve_product("task_1", "B001")
        review_workflow.reject_product("task_1", "B002")

        summary = review_workflow.get_review_summary("task_1")
        assert summary["total"] == 2
        assert summary["approved"] == 1
        assert summary["rejected"] == 1
        assert summary["pending"] == 0
        assert summary["approval_rate"] == 0.5

    def test_approve_nonexistent_product(self, review_workflow, sample_amazon_products):
        """测试批准不存在的产品"""
        review_workflow.submit_for_review("task_1", sample_amazon_products)
        result = review_workflow.approve_product("task_1", "FAKE_ASIN")
        assert result is False

    def test_clear_task(self, review_workflow, sample_amazon_products):
        """测试清理任务数据"""
        review_workflow.submit_for_review("task_1", sample_amazon_products)
        review_workflow.approve_product("task_1", "B001")
        review_workflow.clear_task("task_1")

        assert review_workflow.get_approved("task_1") == []
        assert review_workflow.get_pending("task_1") == []
        assert review_workflow.get_review_summary("task_1") is None


# ═══════════════════════════════════════════════════════
# DiscoveryService Tests
# ═══════════════════════════════════════════════════════


class TestDiscoveryService:
    """测试产品发现服务"""

    @pytest.mark.asyncio
    async def test_discover_products(self, discovery_service, mock_spider, mock_rules):
        """测试发现产品"""
        from app.core.scanner import ScanTask

        task = ScanTask("test_task", "Dogs", 10)
        expected_products = [
            AmazonProduct(
                asin="B001",
                title="Dog Bed",
                category="Dogs",
                rank=100,
            )
        ]
        mock_spider.scrape.return_value = expected_products
        # 设置过滤规则通过所有产品
        mock_rules.filter_amazon_products.return_value = (expected_products, [], {})

        products = await discovery_service.discover(task)

        assert len(products) == 1
        assert products[0].asin == "B001"
        mock_spider.scrape.assert_called_once()

    @pytest.mark.asyncio
    async def test_discover_with_bsr_url(self, discovery_service, mock_spider, mock_rules):
        """测试使用自定义 BSR URL"""
        from app.core.scanner import ScanTask

        task = ScanTask("test_task", "Dogs", 10)
        bsr_url = "https://example.com/bsr"
        # 设置过滤规则通过所有产品
        mock_rules.filter_amazon_products.return_value = ([], [], {})

        await discovery_service.discover(task, bsr_url=bsr_url)

        call_kwargs = mock_spider.scrape.call_args[1]
        assert call_kwargs["bsr_url"] == bsr_url

    @pytest.mark.asyncio
    async def test_enrich_products(self, discovery_service, mock_spider):
        """测试丰富产品信息"""
        products = [AmazonProduct(asin="B001", title="Dog Bed", category="Dogs", rank=100)]
        enriched = [
            AmazonProduct(
                asin="B001",
                title="Dog Bed - Premium Quality",
                category="Dogs",
                rank=100,
                brand="PremiumBrand",
            )
        ]
        mock_spider.enrich_products.return_value = enriched

        result = await discovery_service.enrich_products(products)

        assert len(result) == 1
        assert result[0].brand == "PremiumBrand"
        mock_spider.enrich_products.assert_called_once_with(products)

    def test_filter_products(self, discovery_service, mock_rules):
        """测试过滤产品"""
        products = [
            AmazonProduct(asin="B001", title="Product 1", category="Dogs", rank=100, price=30.0),
            AmazonProduct(asin="B002", title="Product 2", category="Dogs", rank=200, price=150.0),
        ]
        mock_rules.filter_amazon_products.return_value = (products[:1], products[1:], {})

        result = discovery_service.filter_products(products)

        mock_rules.filter_amazon_products.assert_called_once_with(products)
        assert result == products[:1]


# ═══════════════════════════════════════════════════════
# MatchingService Tests
# ═══════════════════════════════════════════════════════


class TestMatchingService:
    """测试匹配服务"""

    @pytest.mark.asyncio
    async def test_match_single_product(
        self, matching_service, mock_matcher, sample_amazon_products
    ):
        """测试单个产品匹配"""
        alibaba_product = AlibabaProduct(
            item_id="100001",
            title="狗窝",
            price=150.0,
            min_order_qty=10,
        )
        mock_matcher.search_and_match.return_value = alibaba_product

        result = await matching_service.match_single_product(sample_amazon_products[0])

        assert result is not None
        assert result.amazon.asin == "B001"
        assert result.alibaba.item_id == "100001"
        mock_matcher.search_and_match.assert_called_once()

    @pytest.mark.asyncio
    async def test_match_single_product_no_match(
        self, matching_service, mock_matcher, sample_amazon_products
    ):
        """测试单个产品未匹配到"""
        mock_matcher.search_and_match.return_value = None

        result = await matching_service.match_single_product(sample_amazon_products[0])

        assert result is None

    @pytest.mark.asyncio
    async def test_match_products_multiple(
        self, matching_service, mock_matcher, sample_amazon_products
    ):
        """测试批量匹配"""
        alibaba_product = AlibabaProduct(
            item_id="100001",
            title="狗窝",
            price=150.0,
            min_order_qty=10,
        )
        mock_matcher.search_and_match.return_value = alibaba_product

        # Mock scan task
        mock_task = MagicMock()
        mock_task.products = []

        results = await matching_service.match_products(mock_task, sample_amazon_products)

        assert len(results) == 2
        assert all(r is not None for r in results)

    @pytest.mark.asyncio
    async def test_match_products_concurrency_control(self, matching_service, mock_matcher):
        """测试并发控制"""
        import asyncio

        call_times = []

        async def slow_matcher(*args, **kwargs):
            call_times.append(datetime.now())
            await asyncio.sleep(0.1)
            return AlibabaProduct(
                item_id="100001",
                title="Test",
                price=100.0,
                min_order_qty=1,
            )

        mock_matcher.search_and_match.side_effect = slow_matcher

        products = [
            AmazonProduct(asin=f"B00{i}", title=f"Product {i}", category="Dogs", rank=i + 1)
            for i in range(5)
        ]

        mock_task = MagicMock()
        mock_task.products = []

        results = await matching_service.match_products(mock_task, products)

        assert len(results) == 5
        # 并发执行应该比顺序执行快
        # 注意：这只是简单的并发性测试


# ═══════════════════════════════════════════════════════
# ScanOrchestrator Tests
# ═══════════════════════════════════════════════════════


class TestScanOrchestrator:
    """测试扫描协调器"""

    @pytest.mark.asyncio
    async def test_start_discover_only(self, mock_storage, mock_config, mock_spider, mock_rules):
        """测试仅发现模式"""
        # Mock breakout scorer
        mock_breakout_scorer = MagicMock()
        mock_breakout_results = [
            {
                "asin": "B001",
                "title": "Dog Bed",
                "breakout_score": {"total": 75.0, "grade": "A级潜力"},
            }
        ]
        mock_breakout_scorer.score_batch.return_value = mock_breakout_results

        mock_analysis = MagicMock()
        mock_analysis.breakout_scorer = mock_breakout_scorer

        orchestrator = ScanOrchestrator(
            task_manager=TaskManager(),
            discovery=DiscoveryService(mock_spider, mock_rules),
            matching=MagicMock(),
            review=MagicMock(),
            analysis=mock_analysis,
            storage=mock_storage,
        )

        expected_products = [AmazonProduct(asin="B001", title="Dog Bed", category="Dogs", rank=100)]
        mock_spider.scrape.return_value = expected_products
        mock_spider.enrich_products.return_value = expected_products
        # 设置过滤规则通过所有产品
        mock_rules.filter_amazon_products.return_value = (expected_products, [], {})

        task_id = await orchestrator.start_discover_only("Dogs", max_products=10)

        # 等待后台任务完成
        await asyncio.sleep(0)

        assert isinstance(task_id, str)
        assert task_id.startswith("scan_")
        mock_storage.save_products.assert_called_once()
        # 验证爆款评分被调用
        mock_breakout_scorer.score_batch.assert_called_once_with(expected_products, {})

        # 验证任务状态
        task = orchestrator.tasks.get_task(task_id)
        assert task is not None
        assert task.breakout_results == mock_breakout_results
        assert task.approved_count == 1  # 产品应被标记为已批准

    @pytest.mark.asyncio
    async def test_start_quick_scan(
        self, mock_storage, mock_config, mock_spider, mock_rules, mock_matcher, mock_scorer
    ):
        """测试快速扫描模式"""
        # Mock breakout scorer
        mock_breakout_scorer = MagicMock()
        mock_breakout_results = [
            {
                "asin": "B001",
                "title": "Dog Bed",
                "breakout_score": {"total": 80.0, "grade": "S级爆款"},
            }
        ]
        mock_breakout_scorer.score_batch.return_value = mock_breakout_results

        mock_analysis = MagicMock()
        mock_analysis.breakout_scorer = mock_breakout_scorer

        orchestrator = ScanOrchestrator(
            task_manager=TaskManager(),
            discovery=DiscoveryService(mock_spider, mock_rules),
            matching=MatchingService(mock_matcher, mock_scorer, mock_config),
            review=MagicMock(),
            analysis=mock_analysis,
            storage=mock_storage,
        )

        expected_products = [AmazonProduct(asin="B001", title="Dog Bed", category="Dogs", rank=100)]
        mock_spider.scrape.return_value = expected_products
        mock_spider.enrich_products.return_value = expected_products
        mock_matcher.search_and_match.return_value = AlibabaProduct(
            item_id="100001", title="狗窝", price=150.0, min_order_qty=10
        )
        # 设置过滤规则通过所有产品
        mock_rules.filter_amazon_products.return_value = (expected_products, [], {})

        task_id = await orchestrator.start_quick_scan("Dogs", max_products=10)

        # 等待后台任务完成
        await asyncio.sleep(0.5)

        assert isinstance(task_id, str)
        mock_storage.save_products.assert_called_once()
        mock_storage.save_match_results.assert_called_once()

        # Debug: check task status
        task = orchestrator.tasks.get_task(task_id)
        print(f"\nTask status: {task.status if task else 'None'}")
        print(f"Task error: {task.error if task else 'None'}")
        print(f"Approved count: {task.approved_count if task else 'None'}")
        print(f"Match results: {task.match_count if task else 'None'}")

        # 验证爆款评分被调用（含匹配数据）
        mock_breakout_scorer.score_batch.assert_called_once()
        call_args = mock_breakout_scorer.score_batch.call_args
        assert call_args[0][0] == expected_products  # 第一个参数是产品列表
        assert isinstance(call_args[0][1], dict)  # 第二个参数是匹配字典

        # 验证任务完成状态
        task = orchestrator.tasks.get_task(task_id)
        assert task is not None
        assert task.breakout_results == mock_breakout_results

    @pytest.mark.asyncio
    async def test_cancel_task(self, mock_storage, mock_config, mock_spider, mock_rules):
        """测试取消任务"""
        orchestrator = ScanOrchestrator(
            task_manager=TaskManager(),
            discovery=DiscoveryService(mock_spider, mock_rules),
            matching=MagicMock(),
            review=MagicMock(),
            analysis=MagicMock(),
            storage=mock_storage,
        )

        task_id = await orchestrator.start_discover_only("Dogs", max_products=10)
        result = orchestrator.cancel_task(task_id)

        assert result is True

    def test_get_task_status(self, mock_storage, mock_config, mock_spider, mock_rules):
        """测试获取任务状态"""
        orchestrator = ScanOrchestrator(
            task_manager=TaskManager(),
            discovery=DiscoveryService(mock_spider, mock_rules),
            matching=MagicMock(),
            review=MagicMock(),
            analysis=MagicMock(),
            storage=mock_storage,
        )

        task = orchestrator.tasks.create_task("Dogs", 10)
        status = orchestrator.get_task_status(task.task_id)

        assert status is not None
        assert status["task_id"] == task.task_id
