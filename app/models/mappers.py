"""
模型映射器 — Pydantic ↔ ORM 转换

职责：
- 在 Pydantic 模型（业务逻辑层）和 SQLAlchemy ORM 模型（持久化层）之间转换
- 提供清晰的层次分离：API 使用 Pydantic，数据库使用 ORM
- 避免直接在业务代码中混合两种模型

架构：
- Pydantic 模型（models/product.py）用于 API 请求/响应和业务逻辑
- ORM 模型（services/storage.py）用于数据库持久化
- 本模块提供两者之间的显式转换函数

使用示例:
    ```python
    from app.models.product import AmazonProduct
    from app.models.mappers import pydantic_to_orm_product, orm_to_pydantic_product

    # Pydantic → ORM
    pydantic_product = AmazonProduct(asin="B00...", title="...", ...)
    orm_product = pydantic_to_orm_product(pydantic_product)

    # ORM → Pydantic
    orm_product = session.get(ProductORM, 1)
    pydantic_product = orm_to_pydantic_product(orm_product)
    ```
"""

from typing import Optional, Dict, Any, List
from datetime import datetime

from app.models.product import AmazonProduct, AlibabaProduct, MatchResult

# ═══════════════════════════════════════════════════════
# ORM 模型定义（临时放在这里，未来迁移到 models/orm.py）
# ═══════════════════════════════════════════════════════

from sqlalchemy import Column, String, Float, Integer, DateTime, Text, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ProductORM(Base):
    """Amazon 商品 ORM 模型（临时）"""

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asin = Column(String(20), unique=True, nullable=False, index=True)
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
    scraped_at = Column(DateTime, default=datetime.now)


class AlibabaProductORM(Base):
    """1688 商品 ORM 模型（临时）"""

    __tablename__ = "alibaba_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(String(50), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    price = Column(Float, nullable=False)
    min_order_qty = Column(Integer, default=1)
    supplier = Column(String(100), nullable=False)
    supplier_rating = Column(Float, nullable=True)
    location = Column(String(200), nullable=True)
    image_url = Column(String(500), nullable=True)
    item_url = Column(String(500), nullable=True)
    matched_score = Column(Float, default=0.0)
    scraped_at = Column(DateTime, default=datetime.now)


class MatchResultORM(Base):
    """匹配结果 ORM 模型（临时）"""

    __tablename__ = "match_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    amazon_asin = Column(String(20), nullable=False, index=True)
    alibaba_item_id = Column(String(50), nullable=False, index=True)
    score = Column(Float, nullable=False)
    price_diff_usd = Column(Float, nullable=False)
    estimated_profit_margin = Column(Float, nullable=False)
    total_cost_usd = Column(Float, nullable=False)
    confidence = Column(String(20), nullable=False)
    recommendation = Column(Text, nullable=True)
    matched_at = Column(DateTime, default=datetime.now)


# ═══════════════════════════════════════════════════════
# Pydantic → ORM 转换
# ═══════════════════════════════════════════════════════


def pydantic_to_orm_product(pydantic: AmazonProduct) -> ProductORM:
    """
    将 AmazonProduct (Pydantic) 转换为 ProductORM

    Args:
        pydantic: Pydantic AmazonProduct 实例

    Returns:
        ORM ProductORM 实例
    """
    return ProductORM(
        asin=pydantic.asin,
        title=pydantic.title,
        category=pydantic.category,
        rank=pydantic.rank,
        price=pydantic.price,
        rating=pydantic.rating,
        review_count=pydantic.review_count,
        image_url=pydantic.image_url,
        product_url=pydantic.product_url,
        is_prime=pydantic.is_prime,
        brand=pydantic.brand,
        seller=pydantic.seller,
        listing_date=pydantic.listing_date,
        category_path=pydantic.category_path,
        scraped_at=pydantic.scraped_at,
    )


def pydantic_to_orm_alibaba(pydantic: AlibabaProduct) -> AlibabaProductORM:
    """
    将 AlibabaProduct (Pydantic) 转换为 AlibabaProductORM

    Args:
        pydantic: Pydantic AlibabaProduct 实例

    Returns:
        ORM AlibabaProductORM 实例
    """
    return AlibabaProductORM(
        item_id=pydantic.item_id,
        title=pydantic.title,
        price=pydantic.price,
        min_order_qty=pydantic.min_order_qty,
        supplier=pydantic.supplier,
        supplier_rating=pydantic.supplier_rating,
        location=pydantic.location,
        image_url=pydantic.image_url,
        item_url=pydantic.item_url,
        matched_score=pydantic.matched_score,
        scraped_at=pydantic.scraped_at,
    )


def pydantic_to_orm_match(pydantic: MatchResult) -> MatchResultORM:
    """
    将 MatchResult (Pydantic) 转换为 MatchResultORM

    Args:
        pydantic: Pydantic MatchResult 实例

    Returns:
        ORM MatchResultORM 实例
    """
    return MatchResultORM(
        amazon_asin=pydantic.amazon.asin,
        alibaba_item_id=pydantic.alibaba.item_id,
        score=pydantic.score,
        price_diff_usd=pydantic.price_diff_usd,
        estimated_profit_margin=pydantic.estimated_profit_margin,
        total_cost_usd=pydantic.total_cost_usd,
        confidence=pydantic.confidence,
        recommendation=pydantic.recommendation,
        matched_at=pydantic.matched_at,
    )


# ═══════════════════════════════════════════════════════
# ORM → Pydantic 转换
# ═══════════════════════════════════════════════════════


def orm_to_pydantic_product(orm: ProductORM) -> AmazonProduct:
    """
    将 ProductORM 转换为 AmazonProduct (Pydantic)

    Args:
        orm: ORM ProductORM 实例

    Returns:
        Pydantic AmazonProduct 实例
    """
    return AmazonProduct(
        asin=orm.asin,
        title=orm.title,
        category=orm.category,
        rank=orm.rank,
        price=orm.price,
        rating=orm.rating,
        review_count=orm.review_count,
        image_url=orm.image_url,
        product_url=orm.product_url,
        is_prime=orm.is_prime,
        brand=orm.brand,
        seller=orm.seller,
        listing_date=orm.listing_date,
        category_path=orm.category_path,
        scraped_at=orm.scraped_at,
    )


def orm_to_pydantic_alibaba(orm: AlibabaProductORM) -> AlibabaProduct:
    """
    将 AlibabaProductORM 转换为 AlibabaProduct (Pydantic)

    Args:
        orm: ORM AlibabaProductORM 实例

    Returns:
        Pydantic AlibabaProduct 实例
    """
    return AlibabaProduct(
        item_id=orm.item_id,
        title=orm.title,
        price=orm.price,
        min_order_qty=orm.min_order_qty,
        supplier=orm.supplier,
        supplier_rating=orm.supplier_rating,
        location=orm.location,
        image_url=orm.image_url,
        item_url=orm.item_url,
        matched_score=orm.matched_score,
        scraped_at=orm.scraped_at,
    )


def orm_to_pydantic_match(orm: MatchResultORM) -> MatchResult:
    """
    将 MatchResultORM 转换为 MatchResult (Pydantic)

    注意：这需要额外查询 AmazonProduct 和 AlibabaProduct

    Args:
        orm: ORM MatchResultORM 实例

    Returns:
        Pydantic MatchResult 实例

    Raises:
        ValueError: 如果关联的 Amazon/1688 产品不存在
    """
    # TODO: 实际使用时需要从数据库加载关联的 AmazonProduct 和 AlibabaProduct
    # 这里先返回一个最小化的 MatchResult
    # 实际实现需要注入 session 或 repository
    raise NotImplementedError(
        "orm_to_pydantic_match 需要访问数据库来加载关联的 Amazon/1688 产品。"
        "请在 StorageService 中实现此逻辑，或使用 batch conversion 方法。"
    )


# ═══════════════════════════════════════════════════════
# 批量转换辅助函数
# ═══════════════════════════════════════════════════════


def batch_pydantic_to_orm_products(pydantic_list: List[AmazonProduct]) -> List[ProductORM]:
    """批量转换 AmazonProduct 列表"""
    return [pydantic_to_orm_product(p) for p in pydantic_list]


def batch_orm_to_pydantic_products(orm_list: List[ProductORM]) -> List[AmazonProduct]:
    """批量转换 ProductORM 列表"""
    return [orm_to_pydantic_product(orm) for orm in orm_list]


def batch_pydantic_to_orm_matches(pydantic_list: List[MatchResult]) -> List[MatchResultORM]:
    """批量转换 MatchResult 列表"""
    return [pydantic_to_orm_match(m) for m in pydantic_list]
