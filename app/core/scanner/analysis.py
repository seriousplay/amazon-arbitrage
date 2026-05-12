"""
AnalysisService - 市场分析服务

职责：
- 协调各种市场分析功能
- 提供 Breakout 检测、市场集中度分析、新品分析、评论分析、趋势分析
"""

from typing import List, Optional

from app.models.product import AmazonProduct
from app.core.breakout_scorer import BreakoutScorer
from app.core.concentration import MarketConcentrationAnalyzer
from app.core.newproduct import NewProductAnalyzer
from app.core.review_crawler import ReviewCrawler
from app.core.review_analyzer import ReviewAnalyzer
from app.core.trends import TrendEngine
from app.config import settings


class AnalysisService:
    """市场分析服务"""

    def __init__(self, config=settings):
        """
        初始化 AnalysisService

        Args:
            config: 配置对象
        """
        self.config = config
        self.breakout_scorer = BreakoutScorer(config)
        self.concentration_analyzer = MarketConcentrationAnalyzer()
        self.new_product_analyzer = NewProductAnalyzer()
        self.review_crawler = ReviewCrawler(config)
        self.review_analyzer = ReviewAnalyzer()
        self.trend_engine = TrendEngine()

    async def analyze_breakout(
        self,
        products: List[AmazonProduct],
    ) -> List[dict]:
        """
        分析 Breakout 产品潜力

        Args:
            products: Amazon 产品列表

        Returns:
            Breakout 分析结果列表
        """
        results = []
        for product in products:
            score = self.breakout_scorer.calculate_breakout_score(product)
            results.append(
                {
                    "asin": product.asin,
                    "title": product.title,
                    "breakout_score": score,
                    "is_breakout": score >= 70,
                }
            )
        return results

    async def analyze_concentration(
        self,
        products: List[AmazonProduct],
    ) -> dict:
        """
        分析市场集中度

        Args:
            products: Amazon 产品列表

        Returns:
            市场集中度分析结果
        """
        return self.concentration_analyzer.analyze(products)

    async def analyze_new_products(
        self,
        products: List[AmazonProduct],
        days: int = 30,
    ) -> dict:
        """
        分析新品机会

        Args:
            products: Amazon 产品列表
            days: 考虑最近多少天内的新品

        Returns:
            新品分析结果
        """
        return self.new_product_analyzer.analyze(products, days=days)

    async def analyze_reviews(
        self,
        products: List[AmazonProduct],
    ) -> dict:
        """
        分析评论数据

        Args:
            products: Amazon 产品列表

        Returns:
            评论分析结果
        """
        # 爬取评论数据
        reviews_data = await self.review_crawler.crawl_products(products)

        # 分析评论情感
        sentiment = self.review_analyzer.analyze_batch(reviews_data)

        return {
            "total_reviews": sum(r.get("review_count", 0) for r in reviews_data),
            "average_rating": (
                sum(r.get("rating", 0) for r in reviews_data) / len(reviews_data)
                if reviews_data
                else 0
            ),
            "sentiment": sentiment,
        }

    async def analyze_trends(
        self,
        products: List[AmazonProduct],
    ) -> dict:
        """
        分析市场趋势

        Args:
            products: Amazon 产品列表

        Returns:
            趋势分析结果
        """
        return self.trend_engine.analyze(products)
