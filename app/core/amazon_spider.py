"""
Amazon BSR 爬虫 - 异步采集 Amazon Best Sellers 榜单商品数据
"""

import asyncio
import random
import re
from typing import List, Optional
from bs4 import BeautifulSoup
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..models.product import AmazonProduct
from ..utils.logger import get_logger

logger = get_logger(__name__)

# User-Agent 轮换池
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
]


class AmazonBSRSpider:
    """Amazon BSR 榜单爬虫 — 异步采集、自动重试、UA 轮换"""

    MAX_PRODUCTS_PER_PAGE = 50  # 每页最多处理的商品数上限

    def __init__(self, config):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        """惰性初始化 HTTP 客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": random.choice(USER_AGENTS)},
                follow_redirects=True,
            )
        return self._client

    async def scrape(
        self, category: str, max_pages: int = 1, max_products: int = 20,
        bsr_url: str = None,
    ) -> List[AmazonProduct]:
        """爬取 Amazon BSR 榜单。

        Args:
            category: 类目名称（如 Electronics）
            max_pages: 最大爬取页数
            max_products: 最大返回商品数
            bsr_url: 类目 BSR URL 路径，如 /Best-Sellers-Electronics/zgbs/electronics/

        Returns:
            AmazonProduct 列表
        """
        products: List[AmazonProduct] = []
        bsr_path = bsr_url or "/Best-Sellers-Pet-Supplies/zgbs/pet-supplies/"

        for page in range(1, max_pages + 1):
            if len(products) >= max_products:
                break

            url = f"https://www.amazon.com{bsr_path}?pg={page}"
            html = await self._fetch_page(url, page)

            if html is None:
                continue

            page_products = self._parse_page(html, category)
            products.extend(page_products)

            # 控制爬取速度：随机延迟，降低被反爬概率
            delay = random.uniform(
                self.config.REQUEST_DELAY_MIN,
                self.config.REQUEST_DELAY_MAX,
            )
            await asyncio.sleep(delay)

        # 截断到 max_products
        products = products[:max_products]
        logger.info(f"✓ 解析完成: {category} - {len(products)} 个商品")
        return products

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
    )
    async def _fetch_page(self, url: str, page: int) -> Optional[str]:
        """获取单页 HTML，带自动重试和 UA 轮换"""
        logger.info(f"获取页面: 第{page}页 - {url}")
        self.client.headers["User-Agent"] = random.choice(USER_AGENTS)
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.text

    def _parse_page(self, html: str, category: str) -> List[AmazonProduct]:
        """从 HTML 中解析商品数据（多选择器回退，适应 Amazon 页面变化）"""
        soup = BeautifulSoup(html, "html.parser")

        # 尝试多种容器选择器
        items = []
        for sel in [
            "div[data-asin]",
            "div.zg-item",
            "div.p13n-sc-uncoverable-faceout",
            "div[id^='zg-immersive']",
            "div.a-carousel-card",
        ]:
            items = soup.select(sel)
            if items:
                break

        # 如果还是找不到，尝试更宽泛的选择器
        if not items:
            items = soup.select("div[data-asin], li[data-asin], div[id*='item']")

        products: List[AmazonProduct] = []
        seen_asins = set()

        for item in items:
            asin = item.get("data-asin") or ""
            if not asin:
                link = item.select_one("a[href*='/dp/']")
                if link:
                    m = re.search(r"/dp/([A-Z0-9]{10})", link.get("href", ""))
                    if m:
                        asin = m.group(1)
            if not asin or asin in seen_asins:
                continue
            seen_asins.add(asin)

            title = self._extract_title(item)
            rank = self._extract_rank(item)
            price = self._extract_price(item)
            rating = self._extract_rating(item)
            review_count = self._extract_reviews(item)

            products.append(
                AmazonProduct(
                    asin=asin,
                    title=title,
                    category=category,
                    rank=rank,
                    price=price,
                    rating=rating,
                    review_count=review_count,
                )
            )

        return products

    # ─── 字段提取（多选择器回退）─────────────────────────

    def _extract_title(self, item) -> str:
        selectors = [
            "div[class*='Title'] span", "div[class*='title'] span",
            "span[class*='Title']", "span[class*='title']",
            "a[class*='Title'] span", "a[class*='title'] span",
            "h2 a span", "h2 span",
            "div.p13n-sc-truncate-desktop-type2",
            "div.p13n-sc-truncated",
            "div._cDEzb_p13n-sc-css-line-clamp-3_g3dy1",
            "div._cDEzb_p13n-sc-css-line-clamp-4_g3dy1",
            "img[alt]",  # 最后的回退：用图片 alt
        ]
        for sel in selectors:
            el = item.select_one(sel)
            if el:
                text = el.get("alt") or el.get_text(strip=True)
                if text and len(text) > 3:
                    return text

        # 终极回退：提取任何看起来像标题的文本
        texts = [t.strip() for t in item.stripped_strings if len(t.strip()) > 10]
        return texts[0] if texts else "Unknown"

    def _extract_rank(self, item) -> int:
        for sel in [
            "span.zg-bdg-text", "span.zg-bdg-body",
            "span[class*='rank']", "span[class*='Rank']",
            "span:contains('#')",
        ]:
            el = item.select_one(sel)
            if el:
                text = el.get_text(strip=True).replace("#", "").replace(",", "")
                try:
                    return int(text)
                except ValueError:
                    pass
        return 0

    def _extract_price(self, item):
        for sel in [
            "span.a-price span.a-offscreen",
            "span.a-price",
            "span[class*='price']", "span[class*='Price']",
            "span._cDEzb_p13n-sc-price_3mJ9Z",
            "span.a-color-price",
        ]:
            el = item.select_one(sel)
            if el:
                text = el.get_text(strip=True).replace("$", "").replace(",", "")
                try:
                    return float(text)
                except ValueError:
                    pass
        return None

    def _extract_rating(self, item):
        for sel in [
            "i.a-icon-star span.a-icon-alt",
            "i.a-icon-star-small span.a-icon-alt",
            "span.a-icon-alt",
            "i[class*='star'] span",
            "span[aria-label*='out of']",
        ]:
            el = item.select_one(sel)
            if el:
                text = el.get("aria-label") or el.get_text(strip=True)
                try:
                    return float(text.split()[0])
                except (ValueError, IndexError):
                    pass
        return None

    def _extract_reviews(self, item):
        for sel in [
            "a.a-size-small", "a.a-link-normal",
            "span.a-size-small", "span.a-size-base",
            "span[class*='review']", "a[class*='review']",
        ]:
            el = item.select_one(sel)
            if el:
                text = el.get_text(strip=True).replace(",", "")
                m = re.search(r"([\d,]+)", text)
                if m:
                    return int(m.group(1).replace(",", ""))
        return None

    async def enrich_product(self, product: "AmazonProduct") -> "AmazonProduct":
        """抓取 ASIN 详情页，补充多语言标题、品牌等信息"""
        try:
            url = f"https://www.amazon.com/dp/{product.asin}"
            resp = await self.client.get(
                url,
                headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
            )
            if resp.status_code != 200:
                return product

            soup = BeautifulSoup(resp.text, "html.parser")

            # 提取完整标题（仅当详情页标题合理时才替换）
            title_el = soup.select_one("#productTitle")
            if title_el:
                full_title = title_el.get_text(strip=True)
                # 只替换标题长度至少为原标题的70%且不超过3倍（防误抓）
                if full_title and len(full_title) >= len(product.title) * 0.7 and len(full_title) <= len(product.title) * 3:
                    product.title = full_title

            # 提取品牌（多种选择器回退）
            brand = None
            for sel in [
                "#bylineInfo", "a#bylineInfo", "#brand",
                ".po-brand span.a-size-base", "#productOverview_feature_div .a-row span",
                "[data-feature-name='brand']", "#detail-bullets b:contains('Brand')",
            ]:
                brand_el = soup.select_one(sel)
                if brand_el:
                    brand = brand_el.get_text(strip=True)
                    if brand and "Visit the" in brand:
                        brand = brand.replace("Visit the", "").replace("Store", "").strip()
                    if brand:
                        break

            if brand and not product.brand:
                product.brand = brand

            # 尝试从 title 提取品牌（格式 "Brand Name Product Title"）
            if not product.brand and product.title:
                words = product.title.split()
                if len(words) > 1 and words[0][0].isupper():
                    # 首个全大写单词可能是品牌
                    product.brand = words[0]

            # 提取卖家信息（用于卖家集中度分析）
            seller = None
            for sel in [
                "#sellerInfoTrigger", "#merchant-info",
                "a[href*='seller=']", "a#bylineInfo",
                "div#merchant-info",
                "div.a-box-inner a[href*='seller']",
            ]:
                seller_el = soup.select_one(sel)
                if seller_el:
                    seller = seller_el.get_text(strip=True)
                    if seller and len(seller) > 2:
                        # 清理多余文本
                        seller = seller.replace("Visit the", "").replace("Store", "").replace("Brand:", "").strip()
                        if seller:
                            break
            if seller and len(seller) > 1:
                product.seller = seller[:200]

            # 提取首次上架日期（用于新品率分析）
            import re as _re
            listing_date = None
            for sel in [
                "#productDetails_detailBullets_sections1",
                "#detailBullets_feature_div",
                "#productDetails_techSpec_section_1",
                "div#prodDetails",
            ]:
                container = soup.select_one(sel)
                if not container:
                    continue
                text = container.get_text()
                # 匹配 "Date First Available: January 1, 2024" 或 "首次上架日期：2024年1月1日"
                m = _re.search(
                    r'(?:Date First Available|首次上架日期)[：:]\s*(.+?)(?:\)|$|\n)',
                    text, _re.IGNORECASE
                )
                if m:
                    listing_date = m.group(1).strip()
                    break
            if listing_date:
                product.listing_date = listing_date[:50]

            # 提取类目路径
            cat_els = soup.select("#wayfinding-breadcrumbs_feature_div li a, #breadCrumb a")
            if cat_els:
                product.category_path = " > ".join(
                    el.get_text(strip=True) for el in cat_els
                ) or None

        except Exception as e:
            logger.debug(f"详情页抓取失败 {product.asin}: {e}")

        return product

    async def enrich_products(
        self, products: List["AmazonProduct"], concurrency: int = 5
    ) -> List["AmazonProduct"]:
        """批量抓取详情页丰富商品信息"""
        sem = asyncio.Semaphore(concurrency)

        async def enrich_one(p):
            async with sem:
                await asyncio.sleep(random.uniform(0.5, 1.5))
                return await self.enrich_product(p)

        tasks = [enrich_one(p) for p in products]
        return await asyncio.gather(*tasks)

    async def deep_crawl(
        self, category: str, bsr_url: str = None,
        max_products: int = 100, enrich_concurrency: int = 10,
    ) -> List[AmazonProduct]:
        """深度爬取 — 获取 Top N BSR 商品并丰富详情（用于集中度分析）

        与普通 scrape 的区别：
        - 爬取更多页面（确保达到 max_products）
        - 更高的 enrich 并发
        - 强制采集 seller 信息
        """
        bsr_path = bsr_url or "/Best-Sellers-Pet-Supplies/zgbs/pet-supplies/"

        # 确定需要的页数（每页最多 50 个）
        pages_needed = (max_products // 50) + 2  # 多跑一页确保覆盖
        products = []

        for page in range(1, pages_needed + 1):
            if len(products) >= max_products:
                break

            url = f"https://www.amazon.com{bsr_path}?pg={page}"
            html = await self._fetch_page(url, page)

            if html is None:
                logger.warning(f"deep_crawl: 第{page}页获取失败，跳过")
                continue

            page_items = self._parse_page(html, category)
            products.extend(page_items)
            logger.info(f"deep_crawl: 第{page}页 → {len(page_items)} 个商品")

            # 控制爬取速度
            delay = random.uniform(
                self.config.REQUEST_DELAY_MIN,
                self.config.REQUEST_DELAY_MAX,
            )
            await asyncio.sleep(delay)

        products = products[:max_products]
        logger.info(
            f"deep_crawl: {category} 共获取 {len(products)} 个商品"
        )

        if not products:
            return products

        # 详情丰富（高并发）
        logger.info(
            f"deep_crawl: 开始丰富 {len(products)} 个商品详情"
            f"（并发={enrich_concurrency}）"
        )
        products = await self.enrich_products(
            products, concurrency=enrich_concurrency
        )

        return products

    async def cleanup(self):
        """关闭 HTTP 客户端"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
