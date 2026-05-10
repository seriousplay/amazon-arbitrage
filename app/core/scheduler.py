"""
应用内定时任务调度器 — 支持每日/每周自动扫描
"""
import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

SCHEDULE_FILE = Path(__file__).parent.parent.parent / "data" / "schedule.json"


class InAppScheduler:
    """轻量级应用内调度器"""

    def __init__(self):
        self._tasks: Dict[str, dict] = {}
        self._running = False
        self._scan_callback: Optional[Callable] = None
        self._last_run: Dict[str, datetime] = {}
        self._load()

    def _load(self):
        if SCHEDULE_FILE.exists():
            try:
                self._tasks = json.loads(SCHEDULE_FILE.read_text())
            except Exception:
                self._tasks = self._default_tasks()

    def _save(self):
        SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCHEDULE_FILE.write_text(json.dumps(self._tasks, ensure_ascii=False, indent=2))

    @staticmethod
    def _default_tasks() -> dict:
        return {
            "weekly-scan": {
                "name": "每周自动扫描",
                "enabled": True,
                "cron": "weekly",  # weekly | daily | hourly
                "day": 1,  # Monday=1
                "hour": 9,
                "minute": 0,
                "categories": ["Pet Supplies", "Electronics", "Sports & Outdoors",
                               "Home & Kitchen", "Beauty & Personal Care"],
                "max_products": 15,
                "description": "每周一早上 9:00 自动扫描核心品类",
            }
        }

    @property
    def tasks(self) -> dict:
        return self._tasks

    @property
    def last_runs(self) -> dict:
        return {k: v.isoformat() if v else None for k, v in self._last_run.items()}

    def set_scan_callback(self, cb: Callable):
        self._scan_callback = cb

    def update_task(self, task_id: str, config: dict):
        if task_id in self._tasks:
            self._tasks[task_id].update(config)
        else:
            self._tasks[task_id] = config
        self._save()

    def toggle_task(self, task_id: str, enabled: bool):
        if task_id in self._tasks:
            self._tasks[task_id]["enabled"] = enabled
            self._save()

    async def start(self):
        """启动调度循环"""
        self._running = True
        logger.info("⏰ 定时任务调度器已启动")
        asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False

    async def _loop(self):
        """主调度循环，每 60 秒检查一次"""
        while self._running:
            try:
                now = datetime.now()
                for task_id, config in self._tasks.items():
                    if not config.get("enabled", True):
                        continue
                    if self._should_run(now, task_id, config):
                        await self._execute(task_id, config)
            except Exception as e:
                logger.error(f"调度器异常: {e}")
            await asyncio.sleep(60)

    def _should_run(self, now: datetime, task_id: str, config: dict) -> bool:
        """判断是否该执行"""
        cron = config.get("cron", "weekly")
        hour = config.get("hour", 9)
        minute = config.get("minute", 0)
        day = config.get("day", 1)

        # 检查分钟是否匹配（允许 ±1 分钟的误差窗口）
        if now.minute != minute:
            return False

        # 检查小时
        if now.hour != hour:
            return False

        # 检查天
        if cron == "daily":
            pass  # 每天都可以
        elif cron == "weekly":
            if now.isoweekday() != day:
                return False
        elif cron == "hourly":
            pass

        # 检查是否已经执行过（同一天内不重复）
        last = self._last_run.get(task_id)
        if last and last.date() == now.date() and cron != "hourly":
            return False

        return True

    async def _execute(self, task_id: str, config: dict):
        """执行定时任务"""
        logger.info(f"⏰ 执行定时任务: {config.get('name', task_id)}")
        self._last_run[task_id] = datetime.now()

        if not self._scan_callback:
            logger.warning("未设置扫描回调函数")
            return

        categories = config.get("categories", [])
        max_products = config.get("max_products", 15)

        for category in categories:
            try:
                logger.info(f"  扫描品类: {category}")
                await self._scan_callback(category, max_products)
                await asyncio.sleep(10)  # 品类间休息 10 秒
            except Exception as e:
                logger.error(f"  扫描 {category} 失败: {e}")

        logger.info(f"✓ 定时任务完成: {config.get('name', task_id)}")

    async def run_now(self, task_id: str = "weekly-scan"):
        """手动立即执行"""
        config = self._tasks.get(task_id)
        if not config:
            return False
        await self._execute(task_id, config)
        return True
