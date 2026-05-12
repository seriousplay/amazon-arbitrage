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
"""

from .engine import ScanOrchestrator
from .task import TaskManager
from .discovery import DiscoveryService
from .matching import MatchingService
from .review import ReviewWorkflow
from .analysis import AnalysisService

__all__ = [
    "ScanOrchestrator",
    "TaskManager",
    "DiscoveryService",
    "MatchingService",
    "ReviewWorkflow",
    "AnalysisService",
]
