"""
Amazon 差评爬虫 — 异步采集商品低分评论（1-3 星）
"""

import asyncio
import random
import re
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.models.review import ReviewItem
from app.utils.logger import get_logger

logger = get_logger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
]


class ReviewCrawler:
    """Amazon 评论爬虫 — 异步采集 + 自动重试 + UA 轮换"""

    MAX_REVIEWS_PER_PRODUCT = 50    # 每产品最多爬取评论数
    REVIEWS_PER_PAGE = 10           # Amazon 每页 10 条评论

    def __init__(self, config):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": random.choice(USER_AGENTS)},
                follow_redirects=True,
            )
        return self._client

    async def crawl_reviews(
        self,
        asin: str,
        max_reviews: int = MAX_REVIEWS_PER_PRODUCT,
        min_rating: float = 1.0,
        max_rating: float = 3.0,
    ) -> List[ReviewItem]:
        """爬取指定 ASIN 的低分评论（默认 1-3 星）

        Args:
            asin: Amazon ASIN
            max_reviews: 最大爬取评论数
            min_rating: 最低评分（含）
            max_rating: 最高评分（含）

        Returns:
            ReviewItem 列表（按时间倒序）
        """
        all_reviews: List[ReviewItem] = []
        page = 1

        while len(all_reviews) < max_reviews:
            url = self._build_url(asin, page)
            html = await self._fetch_page(url, asin, page)

            if html is None:
                break

            page_reviews = self._parse_reviews(html, asin)
            if not page_reviews:
                break  # 无更多评论

            # 按评分过滤
            filtered = [
                r for r in page_reviews
                if min_rating <= r.rating <= max_rating
            ]
            all_reviews.extend(filtered)

            logger.info(
                f"评论爬取: {asin} 第{page}页 → "
                f"{len(page_reviews)}条(含{len(filtered)}条差评)"
            )

            page += 1

            # 如果该页没有差评但有很多好评，可能后面都是好评，提前退出
            if len(filtered) == 0 and len(page_reviews) >= self.REVIEWS_PER_PAGE:
                # Amazon 按最有帮助排序，差评可能集中在前面几页
                if page > 3:
                    break

            # 反爬延迟
            await asyncio.sleep(random.uniform(1.5, 3.0))

        result = all_reviews[:max_reviews]
        logger.info(f"评论爬取完成: {asin} → {len(result)} 条差评")
        return result

    def _build_url(self, asin: str, page: int = 1) -> str:
        """构建评论列表页 URL"""
        return (
            f"https://www.amazon.com/product-reviews/{asin}/"
            f"ref=cm_cr_dp_d_show_all_btm?ie=UTF8"
            f"&reviewerType=all_reviews"
            f"&pageNumber={page}"
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
    )
    async def _fetch_page(self, url: str, asin: str, page: int) -> Optional[str]:
        """获取评论页 HTML"""
        self.client.headers["User-Agent"] = random.choice(USER_AGENTS)
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"评论页 404: {asin} page={page}")
                return None
            raise

    def _parse_reviews(self, html: str, asin: str) -> List[ReviewItem]:
        """从 HTML 中解析评论"""
        soup = BeautifulSoup(html, "html.parser")
        reviews = []

        # Amazon 评论容器选择器
        review_elements = soup.select(
            "div[data-hook='review'], "
            "div.review, "
            "div.a-section.review"
        )

        for el in review_elements:
            try:
                # 评分
                rating = None
                rating_el = el.select_one(
                    "i[data-hook='review-star-rating'], "
                    "i.a-icon-star, "
                    "span.a-icon-alt"
                )
                if rating_el:
                    text = rating_el.get("aria-label") or rating_el.get_text(strip=True)
                    m = re.search(r"([\d.]+)\s*out\s*of\s*5", text, re.IGNORECASE)
                    if m:
                        rating = float(m.group(1))

                if rating is None:
                    continue

                # 标题
                title_el = el.select_one(
                    "a[data-hook='review-title'], "
                    "span[data-hook='review-title'], "
                    "a.review-title"
                )
                title = title_el.get_text(strip=True) if title_el else ""

                # 正文
                text_el = el.select_one(
                    "span[data-hook='review-body'], "
                    "div.review-text, "
                    "span.review-text"
                )
                text = text_el.get_text(strip=True) if text_el else ""

                if not text:
                    continue

                # 日期
                date_el = el.select_one(
                    "span[data-hook='review-date'], "
                    "span.review-date"
                )
                date = date_el.get_text(strip=True) if date_el else ""

                # 评论者
                author_el = el.select_one(
                    "a[data-hook='review-author'], "
                    "span.a-profile-name, "
                    "span.review-author"
                )
                author = author_el.get_text(strip=True) if author_el else "Unknown"

                # Verified Purchase
                vp_el = el.select_one("span[data-hook='avp-badge']")
                verified = vp_el is not None

                reviews.append(ReviewItem(
                    asin=asin, rating=rating,
                    title=title[:200], text=text[:2000],
                    date=date[:50], reviewer=author[:50],
                    verified_purchase=verified,
                ))

            except Exception:
                continue

        return reviews

    async def crawl_batch(
        self,
        products: List[tuple],  # [(asin, title), ...]
        max_reviews_per_product: int = 50,
        concurrency: int = 3,
    ) -> dict:
        """批量爬取多个 ASIN 的差评

        Args:
            products: [(asin, title), ...]
            max_reviews_per_product: 每产品最多差评数
            concurrency: 并发爬取数

        Returns:
            {asin: [ReviewItem, ...]}
        """
        sem = asyncio.Semaphore(concurrency)

        async def crawl_one(asin: str, title: str) -> tuple:
            async with sem:
                try:
                    reviews = await self.crawl_reviews(
                        asin, max_reviews=max_reviews_per_product,
                    )
                    return asin, reviews
                except Exception as e:
                    logger.error(f"爬取评论失败 {asin}: {e}")
                    return asin, []

        tasks = [crawl_one(asin, title) for asin, title in products]
        results = await asyncio.gather(*tasks)

        return {asin: reviews for asin, reviews in results}

    async def cleanup(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None
