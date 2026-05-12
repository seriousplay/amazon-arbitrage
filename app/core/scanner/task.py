"""
TaskManager - 内存任务生命周期管理

职责：
- 创建、获取、更新、取消扫描任务
- 管理任务锁（防止并发访问冲突）
- 提供任务统计信息
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional

# 向后兼容：重新导出 ScanTask
from app.core.scanner.models import ScanTask


class TaskManager:
    """管理扫描任务的内存状态"""

    def __init__(self):
        self._tasks: Dict[str, "ScanTask"] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def create_task(self, category: str, max_products: int) -> "ScanTask":
        """创建新扫描任务"""
        from app.core.scanner import ScanTask

        # 使用递增计数器确保唯一性
        if not hasattr(self, "_task_counter"):
            self._task_counter = 0
        self._task_counter += 1

        task_id = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._task_counter}"
        task = ScanTask(
            task_id=task_id,
            category=category,
            max_products=max_products,
        )
        self._tasks[task_id] = task
        self._locks[task_id] = asyncio.Lock()
        return task

    def get_task(self, task_id: str) -> Optional["ScanTask"]:
        """获取指定任务"""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> List["ScanTask"]:
        """获取所有任务"""
        return list(self._tasks.values())

    def update_task(self, task: "ScanTask") -> None:
        """更新任务状态"""
        if task.task_id not in self._tasks:
            raise KeyError(f"Task {task.task_id} not found")
        self._tasks[task.task_id] = task

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = self._tasks.get(task_id)
        if task is None:
            return False

        if task.status in ("completed", "failed", "cancelled"):
            return False

        task.status = "cancelled"
        task.error = "Task cancelled by user"
        task.completed_at = datetime.now()
        return True

    async def acquire_lock(self, task_id: str) -> asyncio.Lock:
        """获取任务锁（用于并发控制）"""
        async with self._global_lock:
            if task_id not in self._locks:
                self._locks[task_id] = asyncio.Lock()
            return self._locks[task_id]

    def get_task_summary(self, task_id: str) -> Optional[dict]:
        """获取任务摘要信息"""
        task = self._tasks.get(task_id)
        if task is None:
            return None
        return task.to_summary()

    def get_statistics(self) -> dict:
        """获取所有任务的统计信息"""
        total = len(self._tasks)
        by_status = {}
        for task in self._tasks.values():
            status = task.status
            by_status[status] = by_status.get(status, 0) + 1

        return {
            "total_tasks": total,
            "by_status": by_status,
            "active_tasks": by_status.get("running", 0) + by_status.get("pending", 0),
        }
