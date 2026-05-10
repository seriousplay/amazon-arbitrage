"""
存储服务 — 数据库抽象层（SQLAlchemy 异步 + SQLite/PostgreSQL）
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

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
        logger.info(f"✓ 保存任务: {task_id} ({match_count} 个匹配, {len(json.dumps(results))} 字节)")

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
            stmt = (
                select(ScanTaskRecord)
                .order_by(desc(ScanTaskRecord.created_at))
                .limit(limit)
            )
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

    async def close(self):
        """关闭数据库连接"""
        if self._async_engine:
            await self._async_engine.dispose()
        self.is_connected = False
        logger.info("✓ 数据库连接已关闭")
