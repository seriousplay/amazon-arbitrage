"""
扫描任务 Worker
"""

import asyncio
from typing import Set
from app.core.scanner import ScanEngine
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ScannerWorker:
    """后台任务 Worker"""

    def __init__(self, scanner: ScanEngine, max_workers: int = 2):
        self.scanner = scanner
        self.max_workers = max_workers
        self._running_tasks: Set[str] = set()
        self._semaphore = asyncio.Semaphore(max_workers)
        self.is_running = False

    async def start(self):
        self.is_running = True
        logger.info(f"✓ Worker 启动（最大并发: {self.max_workers}）")

    async def stop(self):
        self.is_running = False
        logger.info("✓ Worker 停止")

    async def submit(self, task_id: str, **kwargs):
        async with self._semaphore:
            self._running_tasks.add(task_id)
            try:
                await self.scanner.start_scan(**kwargs)
            finally:
                self._running_tasks.discard(task_id)

    @property
    def active_count(self) -> int:
        return len(self._running_tasks)
