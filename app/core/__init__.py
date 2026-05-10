"""核心业务逻辑包"""
from .scanner import ScanEngine, ScanTask
from .amazon_spider import AmazonBSRSpider
from .scorer import MatchScorer

# AlibabaMatcher 需单独导入（避免循环依赖）
def __getattr__(name):
    if name == "AlibabaMatcher":
        from .alibaba_matcher import AlibabaMatcher
        return AlibabaMatcher
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["ScanEngine", "ScanTask", "AmazonBSRSpider", "MatchScorer"]
