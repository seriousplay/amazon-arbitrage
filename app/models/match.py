"""匹配结果模型"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class MatchResult(Base):
    """1688 匹配结果"""
    __tablename__ = "match_results"
    
    id = Column(Integer, primary_key=True, index=True)
    amazon_asin = Column(String, index=True)
    amazon_title = Column(String)
    amazon_price = Column(Float)
    amazon_bsr = Column(String)
    amazon_url = Column(String)
    alibaba_offer_id = Column(String, index=True)
    alibaba_title = Column(String)
    alibaba_price = Column(Float)
    alibaba_min_order = Column(Integer)
    alibaba_supplier = Column(String)
    alibaba_url = Column(String)
    score = Column(Float)
    price_diff = Column(Float)
    price_diff_percent = Column(Float)
    amazon_sales_rank = Column(Integer)
    alibaba_orders = Column(Integer)
    alibaba_rating = Column(Float)
    match_reasons = Column(Text)
    risk_flags = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "amazon_asin": self.amazon_asin,
            "amazon_title": self.amazon_title,
            "amazon_price": self.amazon_price,
            "amazon_bsr": self.amazon_bsr,
            "amazon_url": self.amazon_url,
            "alibaba_offer_id": self.alibaba_offer_id,
            "alibaba_title": self.alibaba_title,
            "alibaba_price": self.alibaba_price,
            "alibaba_min_order": self.alibaba_min_order,
            "alibaba_supplier": self.alibaba_supplier,
            "alibaba_url": self.alibaba_url,
            "score": self.score,
            "price_diff": self.price_diff,
            "price_diff_percent": self.price_diff_percent,
            "amazon_sales_rank": self.amazon_sales_rank,
            "alibaba_orders": self.alibaba_orders,
            "alibaba_rating": self.alibaba_rating,
            "match_reasons": self.match_reasons,
            "risk_flags": self.risk_flags,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class ScanTask(Base):
    """扫描任务记录"""
    __tablename__ = "scan_tasks"
    
    task_id = Column(String, primary_key=True)
    category = Column(String, index=True)
    status = Column(String, default="pending")
    progress = Column(Float, default=0.0)
    amazon_count = Column(Integer, default=0)
    match_count = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            "task_id": self.task_id,
            "category": self.category,
            "status": self.status,
            "progress": self.progress,
            "amazon_count": self.amazon_count,
            "match_count": self.match_count,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
