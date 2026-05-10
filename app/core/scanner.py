"""
扫描引擎 — 三阶段工作流：发现 → 审核 → 匹配
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional

from app.models.product import AmazonProduct, MatchResult
from app.core.amazon_spider import AmazonBSRSpider
from app.core.alibaba_matcher import AlibabaMatcher
from app.core.breakout_scorer import BreakoutScorer
from app.core.concentration import MarketConcentrationAnalyzer
from app.core.newproduct import NewProductAnalyzer
from app.core.review_crawler import ReviewCrawler
from app.core.review_analyzer import ReviewAnalyzer
from app.core.trends import TrendEngine
from app.core.rules import RulesConfig
from app.core.scorer import MatchScorer
from app.models.concentration import ConcentrationResult
from app.services.storage import StorageService
from app.utils.logger import get_logger

logger = get_logger(__name__)

MATCH_CONCURRENCY = 3
MATCH_TIMEOUT = 90
CATEGORIES_FILE = Path(__file__).parent.parent.parent / "data" / "categories.json"


class ProductStatus(str, Enum):
    PENDING = "pending"       # 已发现，待审核
    APPROVED = "approved"     # 已通过审核，待匹配
    REJECTED = "rejected"     # 已拒绝
    MATCHED = "matched"       # 已匹配成功
    NO_MATCH = "no_match"     # 匹配无结果


class Phase(str, Enum):
    DISCOVER = "discover"     # 正在爬取 Amazon
    REVIEW = "review"         # 等待用户审核
    MATCHING = "matching"     # 正在匹配 1688
    DONE = "done"             # 全部完成


@dataclass
class DiscoveredProduct:
    """发现的 Amazon 商品 + 审核状态"""
    product: AmazonProduct
    status: ProductStatus = ProductStatus.PENDING
    match_result: Optional[MatchResult] = None

    def to_dict(self):
        d = self.product.model_dump()
        d["status"] = self.status.value
        if self.match_result:
            d["match"] = self.match_result.model_dump()
        return d


class ScanTask:
    """扫描任务 — 支持分阶段执行"""

    def __init__(self, task_id: str, category: str, max_products: int):
        self.task_id = task_id
        self.category = category
        self.max_products = max_products
        self.phase = Phase.DISCOVER
        self.status = "pending"
        self.progress = 0.0
        self.current_step = ""
        self.products: List[DiscoveredProduct] = []
        self.breakout_results: List[dict] = []
        self.concentration_result: Optional[dict] = None
        self.new_product_analysis: Optional[dict] = None
        self.error: Optional[str] = None
        self.created_at = datetime.now()
        self.completed_at: Optional[datetime] = None

    @property
    def pending_count(self) -> int:
        return sum(1 for p in self.products if p.status == ProductStatus.PENDING)

    @property
    def approved_count(self) -> int:
        return sum(1 for p in self.products if p.status == ProductStatus.APPROVED)

    @property
    def rejected_count(self) -> int:
        return sum(1 for p in self.products if p.status == ProductStatus.REJECTED)

    @property
    def matched_count(self) -> int:
        return sum(1 for p in self.products if p.status == ProductStatus.MATCHED)

    def get_approved_products(self) -> List[AmazonProduct]:
        return [p.product for p in self.products if p.status == ProductStatus.APPROVED]

    def set_product_status(self, asin: str, status: ProductStatus):
        for p in self.products:
            if p.product.asin == asin:
                p.status = status
                return True
        return False

    def approve_all(self):
        for p in self.products:
            if p.status == ProductStatus.PENDING:
                p.status = ProductStatus.APPROVED

    def to_summary(self) -> dict:
        return {
            "task_id": self.task_id,
            "category": self.category,
            "phase": self.phase.value,
            "status": self.status,
            "progress": self.progress,
            "current_step": self.current_step,
            "total": len(self.products),
            "pending": self.pending_count,
            "approved": self.approved_count,
            "rejected": self.rejected_count,
            "matched": self.matched_count,
            "has_concentration": self.concentration_result is not None,
            "has_new_product_analysis": self.new_product_analysis is not None,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class ScanEngine:
    """扫描引擎 — 三阶段工作流"""

    def __init__(self, storage: StorageService, config):
        self.storage = storage
        self.config = config
        self.rules = RulesConfig.load()
        self.amazon_spider = AmazonBSRSpider(config)
        self.alibaba_matcher = AlibabaMatcher(config)
        self.scorer = MatchScorer(config)
        self.breakout_scorer = BreakoutScorer(config)
        self.concentration_analyzer = MarketConcentrationAnalyzer()
        self.new_product_analyzer = NewProductAnalyzer()
        self.review_crawler = ReviewCrawler(config)
        self.review_analyzer = ReviewAnalyzer()
        self.trend_engine = TrendEngine()
        self._tasks: Dict[str, ScanTask] = {}
        self._review_results: dict = {}  # {task_id: ReviewAnalysisBatch.to_dict()}
        self._lock = asyncio.Lock()

    @staticmethod
    def load_categories() -> dict:
        if CATEGORIES_FILE.exists():
            return json.loads(CATEGORIES_FILE.read_text())
        return {"categories": [], "rules": {}}

    # ─── 阶段 1: Amazon 发现（不含1688匹配）────────

    async def start_discover_only(
        self, category: str, max_products: int = 15, bsr_url: str = None,
        callback: Optional[Callable] = None,
    ) -> str:
        """仅执行 Amazon 发现：爬取 + 规则过滤 + 爆款初评（评分不含利润维度）"""
        async with self._lock:
            task_id = str(uuid.uuid4())[:8]
            task = ScanTask(task_id, category, max_products)
            self._tasks[task_id] = task
        asyncio.create_task(self._run_discover_only(task, bsr_url, callback))
        return task_id

    async def _run_discover_only(self, task, bsr_url=None, callback=None):
        try:
            task.status = "running"
            task.phase = Phase.DISCOVER
            task.current_step = "🔍 正在爬取 Amazon BSR..."
            task.progress = 0.1
            await self._notify(callback, task)

            products = await self.amazon_spider.scrape(
                category=task.category, max_pages=min(2, self.config.AMAZON_BSR_PAGES),
                max_products=task.max_products, bsr_url=bsr_url,
            )
            task.current_step = f"📄 已发现 {len(products)} 个商品，正在抓取详情页..."
            task.progress = 0.3
            await self._notify(callback, task)
            products = await self.amazon_spider.enrich_products(products)

            task.current_step = f"📊 规则过滤中..."
            task.progress = 0.6
            passed, filtered, reasons = self.rules.filter_amazon_products(products)
            task.products = [DiscoveredProduct(product=p, status=ProductStatus.APPROVED) for p in passed]
            task.amazon_count = len(passed)

            # 初步评分（不含1688利润数据）
            task.current_step = "📈 生成爆款初评..."
            task.progress = 0.8
            breakout = self.breakout_scorer.score_batch(passed, {})
            task.breakout_results = breakout

            task.phase = Phase.REVIEW  # 等待1688匹配
            task.status = "completed"
            task.progress = 1.0
            task.current_step = f"✅ 发现 {len(passed)} 个潜在商品（规则过滤后），可进行1688匹配"
            task.completed_at = datetime.now()
        except Exception as e:
            logger.error(f"[{task.task_id}] 发现失败: {e}", exc_info=True)
            task.status = "failed"
            task.error = str(e)
        finally:
            await self._notify(callback, task)

    # ─── 阶段 2: 1688 匹配（对已发现的商品）─────────

    async def start_match_only(self, task_id: str, callback=None) -> bool:
        """对已发现的商品执行 1688 匹配"""
        task = self._tasks.get(task_id)
        if not task or not task.products:
            return False
        asyncio.create_task(self._run_match_only(task, callback))
        return True

    async def _run_match_only(self, task, callback=None):
        try:
            task.status = "running"
            task.phase = Phase.MATCHING
            approved = [dp.product for dp in task.products if dp.status == ProductStatus.APPROVED]
            task.current_step = f"🔗 正在匹配 1688 (0/{len(approved)})..."
            task.progress = 0.1
            await self._notify(callback, task)

            results = await self._match_parallel(task, approved, callback)
            task.results = results
            task.match_count = len(results)

            # 更新产品状态
            for r in results:
                for dp in task.products:
                    if dp.product.asin == r.amazon.asin:
                        dp.status = ProductStatus.MATCHED
                        dp.match_result = r

            # 重新评分（含利润维度）
            match_map = {r.amazon.asin: r for r in results}
            breakout = self.breakout_scorer.score_batch(approved, match_map)
            task.breakout_results = breakout

            task.phase = Phase.DONE
            task.status = "completed"
            task.progress = 1.0
            task.current_step = f"✅ 匹配完成: {len(results)} 个1688货源"
            task.completed_at = datetime.now()
        except Exception as e:
            logger.error(f"[{task.task_id}] 匹配失败: {e}", exc_info=True)
            task.status = "failed"
            task.error = str(e)
        finally:
            await self._notify(callback, task)

    # ─── 一键扫描：发现 + 匹配 + 高价值筛选 ──────────

    async def start_quick_scan(
        self,
        category: str,
        max_products: int = 10,
        bsr_url: str = None,
        callback: Optional[Callable] = None,
    ) -> str:
        """一键扫描：发现 → 匹配 → 自动筛选高价值商品"""
        async with self._lock:
            task_id = str(uuid.uuid4())[:8]
            task = ScanTask(task_id, category, max_products)
            self._tasks[task_id] = task

        asyncio.create_task(self._run_quick_scan(task, bsr_url, callback))
        return task_id

    async def _run_quick_scan(
        self, task: ScanTask, bsr_url: str = None, callback: Optional[Callable] = None
    ):
        try:
            task.status = "running"
            task.phase = Phase.DISCOVER

            # Step 1: 爬取 + 丰富详情
            task.current_step = "🔍 正在爬取 Amazon BSR 榜单..."
            task.progress = 0.05
            await self._notify(callback, task)

            products = await self.amazon_spider.scrape(
                category=task.category, max_pages=min(2, self.config.AMAZON_BSR_PAGES),
                max_products=task.max_products, bsr_url=bsr_url,
            )
            task.current_step = f"📄 已发现 {len(products)} 个商品，正在抓取详情页..."
            task.progress = 0.15
            await self._notify(callback, task)
            products = await self.amazon_spider.enrich_products(products)

            # 规则过滤
            passed, filtered, reasons = self.rules.filter_amazon_products(products)
            if not passed:
                task.phase = Phase.DONE
                task.status = "completed"
                task.current_step = "规则过滤后无商品通过"
                task.completed_at = datetime.now()
                return
            task.products = [DiscoveredProduct(product=p, status=ProductStatus.APPROVED) for p in passed]
            task.amazon_count = len(passed)

            task.current_step = f"✅ {len(passed)} 个商品通过规则，准备匹配 1688..."
            task.progress = 0.2
            await self._notify(callback, task)

            # Step 2: 自动匹配
            task.phase = Phase.MATCHING
            task.current_step = f"🔗 正在匹配 1688 (0/{len(passed)})..."
            task.progress = 0.25
            await self._notify(callback, task)
            task.results = await self._match_parallel(task, passed, callback)
            task.match_count = len(task.results)

            # Step 3: 标记高价值
            high_value = [r for r in task.results if r.estimated_profit_margin >= self.rules.min_profit_margin]
            for r in task.results:
                dp = next((d for d in task.products if d.product.asin == r.amazon.asin), None)
                if dp:
                    dp.status = ProductStatus.MATCHED
                    dp.match_result = r
                if r in high_value:
                    r.recommendation = f"🔥 高价值 ({r.estimated_profit_margin:.0f}%利润率) " + r.recommendation

            # 保存
            if task.results:
                await self.storage.save_scan_task(
                    task_id=task.task_id, category=task.category,
                    amazon_count=len(passed), match_count=len(task.results),
                    results=[r.model_dump() for r in task.results],
                )

            # Step 4: 爆款评分
            task.current_step = "爆款评估中..."
            task.progress = 0.9
            await self._notify(callback, task)

            match_map = {r.amazon.asin: r for r in task.results}
            breakout_results = self.breakout_scorer.score_batch(passed, match_map)
            task.breakout_results = breakout_results
            s_count = sum(1 for r in breakout_results if r["breakout_score"]["grade"] in ("S级爆款", "A级潜力"))
            a_count = sum(1 for r in breakout_results if r["breakout_score"]["grade"] == "A级潜力")

            task.phase = Phase.DONE
            task.status = "completed"
            task.progress = 1.0
            task.current_step = f"完成: {len(task.results)} 匹配, {len(high_value)} 高价值, {s_count} S/A级爆款"
            task.completed_at = datetime.now()
        except Exception as e:
            logger.error(f"[{task.task_id}] 一键扫描失败: {e}", exc_info=True)
            task.status = "failed"
            task.error = str(e)
        finally:
            await self._notify(callback, task)

    # ─── 深度市场分析：Top 100 爬取 + 集中度分析 ─────

    async def start_deep_discover(
        self,
        category: str,
        max_products: int = 100,
        bsr_url: str = None,
        callback: Optional[Callable] = None,
    ) -> str:
        """深度市场分析：爬取 Top 100 BSR → 品牌集中度 + 价格区间分析

        对应选品逻辑第 3 条（集中度）和第 5 条（价格区间）。
        此模式不执行 1688 匹配，专注市场格局分析。
        """
        async with self._lock:
            task_id = str(uuid.uuid4())[:8]
            task = ScanTask(task_id, category, max_products)
            self._tasks[task_id] = task

        asyncio.create_task(self._run_deep_discover(task, bsr_url, callback))
        return task_id

    async def _run_deep_discover(
        self, task: ScanTask, bsr_url: str = None,
        callback: Optional[Callable] = None,
    ):
        try:
            task.status = "running"
            task.phase = Phase.DISCOVER

            # Step 1: Top 100 深度爬取
            task.current_step = "深度爬取 Top 100 BSR..."
            task.progress = 0.1
            await self._notify(callback, task)

            products = await self.amazon_spider.deep_crawl(
                category=task.category, bsr_url=bsr_url,
                max_products=task.max_products,
            )

            if not products:
                task.phase = Phase.DONE
                task.status = "completed"
                task.current_step = "爬取失败，无商品数据"
                task.completed_at = datetime.now()
                return

            task.products = [
                DiscoveredProduct(product=p, status=ProductStatus.APPROVED)
                for p in products
            ]

            task.current_step = (
                f"已获取 {len(products)} 个商品，正在进行集中度分析..."
            )
            task.progress = 0.6
            await self._notify(callback, task)

            # Step 2: 品牌集中度 + 价格区间分析
            concentration = self.concentration_analyzer.analyze(
                products=products, category=task.category,
            )
            task.concentration_result = concentration.to_dict()

            # Step 3: 新品渗透分析
            task.current_step = "正在分析新品渗透率..."
            task.progress = 0.8
            await self._notify(callback, task)

            new_product = self.new_product_analyzer.analyze(products)
            task.new_product_analysis = new_product.to_dict()

            # 构建进度提示
            np = task.new_product_analysis
            new_share = np["new_product_rate"]["new_share_percent"]
            top10_new = np["top_10_new_share"]["new_in_top_10"]
            listing_pct = np["listing_date_coverage"]

            task.phase = Phase.DONE
            task.status = "completed"
            task.progress = 1.0
            task.current_step = (
                f"深度分析完成: {len(products)} 个商品, "
                f"{concentration.brand_concentration.total_brands} 个品牌, "
                f"新品率 {new_share:.0f}%"
                f"{f', Top10含{top10_new}个新品' if top10_new > 0 else ''}"
                f"{f' (上架日期覆盖率 {listing_pct:.0f}%)' if listing_pct < 100 else ''} | "
                f"{concentration.overall_verdict}"
            )
            task.completed_at = datetime.now()

            logger.info(
                f"[{task.task_id}] 深度分析完成: "
                f"类别={task.category}, "
                f"产品={len(products)}, "
                f"品牌={concentration.brand_concentration.total_brands}, "
                f"CR3={concentration.brand_concentration.top_3_share:.0f}%, "
                f"HHI={concentration.brand_concentration.hhi:.0f}, "
                f"新品率={new_share:.0f}% ({new_product.new_product_count}/{new_product.with_listing_date})"
            )

        except Exception as e:
            logger.error(
                f"[{task.task_id}] 深度分析失败: {e}", exc_info=True
            )
            task.status = "failed"
            task.error = str(e)
        finally:
            await self._notify(callback, task)

    # ─── 差评分析 ───────────────────────────────────────

    async def start_review_analysis(
        self,
        asins: List[str],
        category: str = "",
        callback: Optional[Callable] = None,
    ) -> str:
        """启动差评分析：爬取评论 → 关键词聚类 → 改进建议"""
        import uuid as _uuid
        task_id = str(_uuid.uuid4())[:8]

        asyncio.create_task(
            self._run_review_analysis(task_id, asins, category, callback)
        )
        return task_id

    async def _run_review_analysis(
        self, task_id: str, asins: List[str],
        category: str, callback: Optional[Callable] = None,
    ):
        try:
            if callback:
                await callback({"task_id": task_id, "current_step": "正在爬取差评...", "progress": 0.1})

            # 爬取差评
            self._review_results[task_id] = {"status": "running", "progress": 0.1}

            # 先用标题占位（实际使用中，可能传入(asin, title)对）
            asin_title_pairs = [(a, a) for a in asins]
            crawled = await self.review_crawler.crawl_batch(
                asin_title_pairs,
                max_reviews_per_product=50,
                concurrency=3,
            )

            if callback:
                await callback({"task_id": task_id, "current_step": "正在分析差评...", "progress": 0.6})

            self._review_results[task_id] = {"status": "analyzing", "progress": 0.6}

            # 分析
            products_reviews = {}
            for asin, reviews in crawled.items():
                # 从已有任务中找标题，或用 ASIN 代替
                title = asin
                for t in self._tasks.values():
                    for dp in t.products:
                        if dp.product.asin == asin:
                            title = dp.product.title
                            break
                if reviews:
                    products_reviews[asin] = (title, reviews)

            if not products_reviews:
                self._review_results[task_id] = {
                    "status": "completed",
                    "progress": 1.0,
                    "error": "未获取到评论数据",
                    "result": None,
                }
                if callback:
                    await callback(self._review_results[task_id])
                return

            batch_result = self.review_analyzer.analyze_batch(
                products_reviews, category=category,
            )
            self._review_results[task_id] = {
                "status": "completed",
                "progress": 1.0,
                "result": batch_result.to_dict(),
            }

            if callback:
                await callback(self._review_results[task_id])

            logger.info(
                f"差评分析完成: {len(products_reviews)} 个产品, "
                f"{sum(len(v) for v in products_reviews.values())} 条评论"
            )

        except Exception as e:
            logger.error(f"差评分析失败: {e}", exc_info=True)
            self._review_results[task_id] = {
                "status": "failed", "error": str(e), "result": None,
            }

    def get_review_analysis(self, task_id: str) -> Optional[dict]:
        """获取差评分析结果"""
        return self._review_results.get(task_id)

    # ─── 趋势引擎管理 ──────────────────────────────────

    def list_trends(self) -> list:
        """列出所有缓存品类趋势"""
        return self.trend_engine.list_all_trends()

    def get_trend(self, keyword: str) -> Optional[dict]:
        """获取指定品类的完整趋势"""
        trend = self.trend_engine.get_category_trend(keyword)
        return trend.to_dict() if trend else None

    def refresh_trends(self) -> dict:
        """用默认数据刷新趋势缓存"""
        self.trend_engine.refresh_from_defaults()
        return {"success": True, "categories": len(self.trend_engine._cache.categories)}

    async def update_trend_from_web(self, keyword: str) -> dict:
        """从网络更新指定品类趋势"""
        ok = await self.trend_engine.update_from_web(keyword)
        return {"success": ok, "keyword": keyword}

    # ─── Phase 1: 发现（传统分步模式）──────────────────

    async def start_discover(
        self,
        category: str,
        max_products: int = 10,
        bsr_url: str = None,
        callback: Optional[Callable] = None,
    ) -> str:
        """启动发现阶段：爬取 Amazon BSR 榜单"""
        async with self._lock:
            task_id = str(uuid.uuid4())[:8]
            task = ScanTask(task_id, category, max_products)
            self._tasks[task_id] = task

        asyncio.create_task(self._run_discover(task, bsr_url, callback))
        return task_id

    async def _run_discover(
        self, task: ScanTask, bsr_url: str = None, callback: Optional[Callable] = None
    ):
        try:
            task.status = "running"
            task.phase = Phase.DISCOVER
            task.current_step = "爬取 Amazon BSR 榜单"
            task.progress = 0.1
            await self._notify(callback, task)

            products = await self.amazon_spider.scrape(
                category=task.category,
                max_pages=min(2, self.config.AMAZON_BSR_PAGES),
                max_products=task.max_products,
                bsr_url=bsr_url,
            )

            # 丰富商品信息（抓取详情页获取多语言标题 + 品牌）
            task.current_step = "丰富商品详情..."
            task.progress = 0.3
            await self._notify(callback, task)
            products = await self.amazon_spider.enrich_products(products)

            # 应用规则过滤
            passed, filtered, reasons = self.rules.filter_amazon_products(products)
            logger.info(
                f"[{task.task_id}] 规则过滤: {len(passed)} 通过 / {len(filtered)} 被过滤"
            )
            for p in filtered[:5]:  # 只记录前5个
                logger.debug(f"  过滤 {p.asin}: {reasons.get(p.asin, [])}")

            # 通过的商品自动标记为已审核
            task.products = [
                DiscoveredProduct(product=p, status=ProductStatus.APPROVED)
                for p in passed
            ]
            task.progress = 1.0

            if not task.products:
                task.phase = Phase.DONE
                task.status = "completed"
                task.current_step = f"发现 {len(products)} 个商品，规则过滤后 0 个通过（放宽规则或检查 data/categories.json）"
                task.completed_at = datetime.now()
                logger.info(f"[{task.task_id}] 规则过滤后无商品通过")
                return

            # 进入审核阶段（已自动通过规则的商品为 approved，如有未通过的为 pending）
            # 被规则过滤掉的不展示
            task.phase = Phase.REVIEW
            task.status = "completed"
            task.current_step = f"发现 {len(products)} 个，规则通过 {len(passed)} 个"
            task.completed_at = datetime.now()
            logger.info(
                f"[{task.task_id}] ✓ 发现 {len(task.products)} 个商品，进入审核"
            )
        except Exception as e:
            logger.error(f"[{task.task_id}] 发现失败: {e}", exc_info=True)
            task.status = "failed"
            task.phase = Phase.DONE
            task.error = str(e)
        finally:
            await self._notify(callback, task)

    # ─── Phase 2: 审核 ─────────────────────────────────

    def approve_product(self, task_id: str, asin: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.phase != Phase.REVIEW:
            return False
        return task.set_product_status(asin, ProductStatus.APPROVED)

    def reject_product(self, task_id: str, asin: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.phase != Phase.REVIEW:
            return False
        return task.set_product_status(asin, ProductStatus.REJECTED)

    def approve_all_products(self, task_id: str) -> int:
        task = self._tasks.get(task_id)
        if not task or task.phase != Phase.REVIEW:
            return 0
        task.approve_all()
        return task.approved_count

    # ─── Phase 3: 匹配 ─────────────────────────────────

    async def start_matching(
        self, task_id: str, callback: Optional[Callable] = None
    ) -> bool:
        """启动匹配阶段：对已审核通过的商品搜索 1688"""
        task = self._tasks.get(task_id)
        if not task or task.phase != Phase.REVIEW:
            return False
        if task.approved_count == 0:
            return False

        asyncio.create_task(self._run_matching(task, callback))
        return True

    async def _run_matching(self, task: ScanTask, callback: Optional[Callable] = None):
        try:
            task.status = "running"
            task.phase = Phase.MATCHING
            task.current_step = "1688 同款匹配中..."
            task.progress = 0.0
            await self._notify(callback, task)

            approved_products = task.get_approved_products()
            semaphore = asyncio.Semaphore(MATCH_CONCURRENCY)
            total = len(approved_products)
            completed = 0

            async def match_one(amz: AmazonProduct):
                nonlocal completed
                async with semaphore:
                    try:
                        ali_list = await asyncio.wait_for(
                            self.alibaba_matcher.search_and_match(
                                amz.title, task.category, amz.category_path
                            ),
                            timeout=MATCH_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        ali_list = []
                    except Exception:
                        ali_list = []

                    completed += 1
                    task.progress = completed / max(total, 1)
                    task.current_step = f"匹配 [{completed}/{total}]"
                    await self._notify(callback, task)

                    if ali_list:
                        result = self.scorer.score_match(
                            amazon=amz, alibaba=ali_list[0]
                        )
                        for dp in task.products:
                            if dp.product.asin == amz.asin:
                                dp.status = ProductStatus.MATCHED
                                dp.match_result = result
                                logger.info(
                                    f"[{task.task_id}] ✓ {amz.asin}: {result.score:.1f}"
                                )
                                return
                    # 无匹配
                    for dp in task.products:
                        if dp.product.asin == amz.asin:
                            dp.status = ProductStatus.NO_MATCH
                            return

            await asyncio.gather(*[match_one(p) for p in approved_products])

            task.phase = Phase.DONE
            task.status = "completed"
            task.progress = 1.0
            task.current_step = f"完成: {task.matched_count} 匹配 / {task.approved_count + task.matched_count + sum(1 for p in task.products if p.status == ProductStatus.NO_MATCH)} 已处理"
            task.completed_at = datetime.now()
            logger.info(
                f"[{task.task_id}] ✓ 匹配完成: {task.matched_count} 个结果"
            )

            # 保存到数据库
            matched = [
                dp.match_result
                for dp in task.products
                if dp.status == ProductStatus.MATCHED and dp.match_result
            ]
            if matched:
                await self.storage.save_scan_task(
                    task_id=task.task_id,
                    category=task.category,
                    amazon_count=len(task.products),
                    match_count=len(matched),
                    results=[r.model_dump() for r in matched],
                )

        except Exception as e:
            logger.error(f"[{task.task_id}] 匹配失败: {e}", exc_info=True)
            task.status = "failed"
            task.error = str(e)
        finally:
            await self._notify(callback, task)

    # ─── 通用 ──────────────────────────────────────────

    async def _notify(self, cb, task):
        if cb:
            await cb(task)

    def get_task(self, task_id: str) -> Optional[ScanTask]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[ScanTask]:
        return list(self._tasks.values())

    async def test_1688_search(self, keyword: str) -> List[dict]:
        products = await self.alibaba_matcher.search_and_match(keyword)
        return [p.model_dump() for p in products]

    async def _match_parallel(self, task: ScanTask, products: List[AmazonProduct], callback) -> List[MatchResult]:
        """并行匹配 Amazon 商品到 1688 供应商"""
        if not products:
            return []
        
        from app.core.alibaba_matcher import AlibabaMatcher
        
        matcher = AlibabaMatcher(config=self.config)
        semaphore = asyncio.Semaphore(3)
        
        async def match_one(product: AmazonProduct) -> Optional[MatchResult]:
            async with semaphore:
                try:
                    result = await matcher.match_amazon_product(
                        asin=product.asin,
                        title=product.title,
                        category=product.category or "Pet Supplies",
                        price=product.price
                    )
                    return result
                except Exception as e:
                    logger.error(f"匹配失败 {product.asin}: {e}")
                    return None
        
        tasks = [match_one(p) for p in products]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid = [r for r in results if r is not None and not isinstance(r, Exception)]
        logger.info(f"匹配完成: {len(valid)}/{len(products)} 成功")
        return valid
    async def cleanup(self):
        await self.amazon_spider.cleanup()
        await self.alibaba_matcher.cleanup()
