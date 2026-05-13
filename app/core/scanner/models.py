"""
扫描工作流遗留类型定义

这些类型定义原本在旧版 scanner.py 中。
为了向后兼容，在此重新定义。
新代码应该使用 ScanOrchestrator + TaskManager 架构，
这些遗留类型仅用于兼容旧代码和测试。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

from app.models.product import AmazonProduct, MatchResult


class ProductStatus(str, Enum):
    """产品状态枚举（遗留，用于向后兼容）"""

    PENDING = "pending"  # 已发现，待审核
    APPROVED = "approved"  # 已通过审核，待匹配
    REJECTED = "rejected"  # 已拒绝
    MATCHED = "matched"  # 已匹配成功
    NO_MATCH = "no_match"  # 匹配无结果


class Phase(str, Enum):
    """扫描阶段枚举（遗留，用于向后兼容）"""

    DISCOVER = "discover"  # 正在爬取 Amazon
    REVIEW = "review"  # 等待用户审核
    MATCHING = "matching"  # 正在匹配 1688
    ANALYSIS = "analysis"  # 正在执行市场分析
    DONE = "done"  # 全部完成


@dataclass
class DiscoveredProduct:
    """发现的 Amazon 商品 + 审核状态（遗留）"""

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
    """扫描任务 — 支持分阶段执行（遗留，用于向后兼容）

    新代码应该使用 TaskManager + ScanOrchestrator 替代。
    """

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
        self.results: List[MatchResult] = []  # 兼容旧版
        self.amazon_count: int = 0
        self.match_count: int = 0

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
