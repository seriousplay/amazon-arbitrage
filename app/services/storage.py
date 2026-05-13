"""
存储服务 — 数据库抽象层（SQLAlchemy 异步 + SQLite/PostgreSQL）
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, Boolean, Float, ForeignKey
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from app.utils.logger import get_logger

logger = get_logger(__name__)

Base = declarative_base()


class ScanTaskRecord(Base):
    """扫描任务记录表"""

    __tablename__ = "scan_tasks"

    id = Column(String, primary_key=True)
    category = Column(String, nullable=False)
    amazon_count = Column(Integer, default=0)
    match_count = Column(Integer, default=0)
    status = Column(String, default="pending")
    results_json = Column(Text, nullable=True)  # JSON 序列化的匹配结果
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)


class ProductRecord(Base):
    """Amazon 产品记录表"""

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, ForeignKey("scan_tasks.id"), nullable=False, index=True)
    asin = Column(String(20), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    category = Column(String(100), nullable=False, index=True)
    rank = Column(Integer, nullable=True)
    price = Column(Float, nullable=True)
    rating = Column(Float, nullable=True)
    review_count = Column(Integer, nullable=True)
    image_url = Column(String(500), nullable=True)
    product_url = Column(String(500), nullable=True)
    is_prime = Column(Boolean, default=False)
    brand = Column(String(100), nullable=True)
    seller = Column(String(200), nullable=True)
    listing_date = Column(String(50), nullable=True)
    category_path = Column(String(200), nullable=True)
    status = Column(String(50), default="pending")  # pending/approved/rejected
    scraped_at = Column(DateTime, default=datetime.now)


class MatchResultRecord(Base):
    """匹配结果记录表"""

    __tablename__ = "match_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, ForeignKey("scan_tasks.id"), nullable=False, index=True)
    amazon_asin = Column(String(20), nullable=False, index=True)
    alibaba_item_id = Column(String(50), nullable=False, index=True)
    score = Column(Float, nullable=False)
    price_diff_usd = Column(Float, nullable=False)
    estimated_profit_margin = Column(Float, nullable=False)
    total_cost_usd = Column(Float, nullable=False)
    confidence = Column(String(20), nullable=False)
    recommendation = Column(Text, nullable=True)
    matched_at = Column(DateTime, default=datetime.now)


class StorageService:
    """存储服务 — 纯异步 SQLAlchemy"""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._async_engine = None
        self.SessionLocal = None
        self.is_connected = False

    async def initialize(self):
        """初始化数据库连接和表结构"""
        self._async_engine = create_async_engine(self.database_url, echo=False)

        # 在异步引擎上创建表
        async with self._async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.SessionLocal = sessionmaker(
            bind=self._async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self.is_connected = True
        logger.info("✓ 数据库初始化完成")

    async def save_scan_task(
        self,
        task_id: str,
        category: str,
        amazon_count: int,
        match_count: int,
        results: List[dict],
    ):
        """保存扫描任务及匹配结果"""
        async with self.SessionLocal() as session:
            record = ScanTaskRecord(
                id=task_id,
                category=category,
                amazon_count=amazon_count,
                match_count=match_count,
                status="completed",
                results_json=json.dumps(results, ensure_ascii=False, default=str),
                completed_at=datetime.now(),
            )
            session.add(record)
            await session.commit()
        logger.info(
            f"✓ 保存任务: {task_id} ({match_count} 个匹配, {len(json.dumps(results))} 字节)"
        )

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务详情（含匹配结果）"""
        async with self.SessionLocal() as session:
            from sqlalchemy import select

            stmt = select(ScanTaskRecord).where(ScanTaskRecord.id == task_id)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if record is None:
                return None
            data = {
                "id": record.id,
                "category": record.category,
                "amazon_count": record.amazon_count,
                "match_count": record.match_count,
                "status": record.status,
                "error": record.error,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "completed_at": record.completed_at.isoformat() if record.completed_at else None,
            }
            if record.results_json:
                try:
                    data["results"] = json.loads(record.results_json)
                except json.JSONDecodeError:
                    data["results"] = []
            else:
                data["results"] = []
            return data

    async def list_recent_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的任务列表"""
        async with self.SessionLocal() as session:
            from sqlalchemy import select, desc

            stmt = select(ScanTaskRecord).order_by(desc(ScanTaskRecord.created_at)).limit(limit)
            result = await session.execute(stmt)
            records = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "category": r.category,
                    "amazon_count": r.amazon_count,
                    "match_count": r.match_count,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in records
            ]

    async def save_products(self, task_id: str, products: List[Any]) -> None:
        """
        保存 Amazon 产品列表到数据库

        Args:
            task_id: 任务ID
            products: AmazonProduct 列表
        """
        from app.models.product import AmazonProduct

        async with self.SessionLocal() as session:
            for product in products:
                if isinstance(product, AmazonProduct):
                    # Convert Pydantic model to dict
                    data = product.model_dump()
                    record = ProductRecord(
                        task_id=task_id,
                        asin=data["asin"],
                        title=data["title"],
                        category=data.get("category", ""),
                        rank=data.get("rank"),
                        price=data.get("price"),
                        rating=data.get("rating"),
                        review_count=data.get("review_count"),
                        image_url=data.get("image_url"),
                        product_url=data.get("product_url"),
                        is_prime=data.get("is_prime", False),
                        brand=data.get("brand"),
                        seller=data.get("seller"),
                        listing_date=data.get("listing_date"),
                        category_path=data.get("category_path"),
                    )
                    session.add(record)
            await session.commit()
        logger.info(f"✓ 保存 {len(products)} 个产品到任务 {task_id}")

    async def save_match_results(self, task_id: str, results: List[Any]) -> None:
        """
        保存匹配结果到数据库

        Args:
            task_id: 任务ID
            results: MatchResult 列表
        """
        from app.models.product import MatchResult

        async with self.SessionLocal() as session:
            for result in results:
                if isinstance(result, MatchResult):
                    data = result.model_dump()
                    record = MatchResultRecord(
                        task_id=task_id,
                        amazon_asin=data["amazon_asin"],
                        alibaba_item_id=data["alibaba_item_id"],
                        score=data.get("score", 0.0),
                        price_diff_usd=data.get("price_diff_usd", 0.0),
                        estimated_profit_margin=data.get("estimated_profit_margin", 0.0),
                        total_cost_usd=data.get("total_cost_usd", 0.0),
                        confidence=data.get("confidence", "low"),
                        recommendation=data.get("recommendation"),
                    )
                    session.add(record)
            await session.commit()
        logger.info(f"✓ 保存 {len(results)} 个匹配结果到任务 {task_id}")

    async def get_task_results(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务结果（含产品清单和匹配状态）

        Args:
            task_id: 任务ID

        Returns:
            包含任务和产品数据的字典，如果任务不存在则返回 None
        """
        async with self.SessionLocal() as session:
            from sqlalchemy import select

            # 获取任务
            task_stmt = select(ScanTaskRecord).where(ScanTaskRecord.id == task_id)
            task_result = await session.execute(task_stmt)
            task_record = task_result.scalar_one_or_none()

            if task_record is None:
                return None

            # 获取产品
            products_stmt = select(ProductRecord).where(ProductRecord.task_id == task_id)
            products_result = await session.execute(products_stmt)
            products = products_result.scalars().all()

            # 获取匹配结果
            matches_stmt = select(MatchResultRecord).where(MatchResultRecord.task_id == task_id)
            matches_result = await session.execute(matches_stmt)
            matches = matches_result.scalars().all()

            return {
                "task": {
                    "id": task_record.id,
                    "category": task_record.category,
                    "status": task_record.status,
                    "amazon_count": task_record.amazon_count,
                    "match_count": task_record.match_count,
                    "error": task_record.error,
                    "created_at": task_record.created_at.isoformat() if task_record.created_at else None,
                    "completed_at": task_record.completed_at.isoformat() if task_record.completed_at else None,
                },
                "products": [
                    {
                        "asin": p.asin,
                        "title": p.title,
                        "category": p.category,
                        "rank": p.rank,
                        "price": p.price,
                        "rating": p.rating,
                        "review_count": p.review_count,
                        "status": p.status,
                    }
                    for p in products
                ],
                "matches": [
                    {
                        "amazon_asin": m.amazon_asin,
                        "alibaba_item_id": m.alibaba_item_id,
                        "score": m.score,
                        "price_diff_usd": m.price_diff_usd,
                        "estimated_profit_margin": m.estimated_profit_margin,
                        "total_cost_usd": m.total_cost_usd,
                        "confidence": m.confidence,
                        "recommendation": m.recommendation,
                    }
                    for m in matches
                ],
            }
        """关闭数据库连接"""
        if self._async_engine:
            await self._async_engine.dispose()
        self.is_connected = False
        logger.info("✓ 数据库连接已关闭")
