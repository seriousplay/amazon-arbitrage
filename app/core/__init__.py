"""核心业务逻辑包

架构说明：
- 所有核心类直接导入，无循环依赖
- AlibabaMatcher 由 scanner.py 直接导入，无需延迟加载
- 已删除 models/match.py (SQLAlchemy ORM)，所有 ORM 模型在 services/storage.py 中定义
"""

from .alibaba_matcher import AlibabaMatcher
from .amazon_spider import AmazonBSRSpider
from .scanner import ScanEngine, ScanTask
from .scorer import MatchScorer

__all__ = ["ScanEngine", "ScanTask", "AmazonBSRSpider", "MatchScorer", "AlibabaMatcher"]
