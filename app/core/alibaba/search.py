"""
SearchHandler - 1688 搜索处理器

职责：
- 将 Amazon 产品转换为 1688 搜索关键词
- 执行搜索请求（HTTP/浏览器）
- 解析搜索结果
- 返回 AlibabaProduct 列表
"""

import asyncio
import re
from typing import List, Optional

from app.models.product import AlibabaProduct as PydanticAlibabaProduct
from app.utils.translator import to_chinese
from app.utils.category_mapper import category_to_search
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SearchHandler:
    """1688 搜索处理器"""

    def __init__(self, browser_controller, use_browser: bool = True):
        """
        初始化 SearchHandler

        Args:
            browser_controller: BrowserController 实例
            use_browser: 是否使用浏览器模式（否则使用 HTTP）
        """
        self.browser = browser_controller
        self.use_browser = use_browser
        self._last_search_url: Optional[str] = None

    def build_search_keyword(
        self,
        title: str,
        category: Optional[str] = None,
        category_path: Optional[str] = None,
    ) -> str:
        """
        构建 1688 搜索关键词

        策略：
        1. 优先使用类目映射（category_path）
        2. 其次使用翻译后的标题（to_chinese）
        3. 回退到英文标题

        Args:
            title: Amazon 产品标题
            category: Amazon 类目名
            category_path: Amazon 完整类目路径

        Returns:
            1688 搜索关键词（中文）
        """
        # 1. 尝试从类目路径映射
        if category_path:
            keyword = category_to_search(category_path, title)
            if keyword:
                logger.debug(f"类目映射关键词: {keyword}")
                return keyword

        # 2. 翻译标题
        chinese_title = to_chinese(title)
        if chinese_title:
            logger.debug(f"翻译关键词: {chinese_title}")
            return chinese_title

        # 3. 回退到原始标题
        logger.debug(f"回退关键词: {title[:50]}")
        return title[:50]

    async def search(
        self,
        keyword: str,
        max_results: int = 20,
    ) -> List[PydanticAlibabaProduct]:
        """
        执行搜索

        Args:
            keyword: 搜索关键词
            max_results: 最大结果数

        Returns:
            AlibabaProduct 列表
        """
        if self.use_browser:
            return await self._search_with_browser(keyword, max_results)
        else:
            return await self._search_http(keyword, max_results)

    async def _search_with_browser(
        self,
        keyword: str,
        max_results: int,
    ) -> List[PydanticAlibabaProduct]:
        """
        使用浏览器模式搜索

        Args:
            keyword: 搜索关键词
            max_results: 最大结果数

        Returns:
            AlibabaProduct 列表
        """
        try:
            page = await self.browser.new_page()

            # 构建搜索 URL
            encoded_keyword = await asyncio.to_thread(
                lambda: __import__('urllib.parse').quote_plus(keyword)
            )
            search_url = f"https://s.1688.com/selloffer/offer_search.htm?keywords={encoded_keyword}"

            logger.info(f"浏览器搜索: {keyword}")
            await page.goto(search_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)  # 等待页面加载

            self._last_search_url = search_url

            # 解析结果
            results = await self._parse_browser_results(page, max_results)

            await page.close()
            return results

        except Exception as e:
            logger.error(f"浏览器搜索失败: {e}")
            return []

    async def _search_http(
        self,
        keyword: str,
        max_results: int,
    ) -> List[PydanticAlibabaProduct]:
        """
        使用 HTTP 模式搜索（降级方案）

        Args:
            keyword: 搜索关键词
            max_results: 最大结果数

        Returns:
            AlibabaProduct 列表
        """
        try:
            import httpx

            encoded_keyword = await asyncio.to_thread(
                lambda: __import__('urllib.parse').quote_plus(keyword)
            )
            search_url = f"https://s.1688.com/selloffer/offer_search.htm?keywords={encoded_keyword}"

            logger.info(f"HTTP 搜索: {keyword}")

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(
                    search_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml",
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    },
                )

                if response.status_code != 200:
                    logger.error(f"HTTP 搜索失败: {response.status_code}")
                    return []

                self._last_search_url = str(response.url)
                return await self._parse_html_results(response.text, keyword, max_results)

        except Exception as e:
            logger.error(f"HTTP 搜索失败: {e}")
            return []

    async def _parse_browser_results(
        self,
        page,
        max_results: int,
    ) -> List[PydanticAlibabaProduct]:
        """
        解析浏览器搜索结果

        Args:
            page: Playwright Page 对象
            max_results: 最大结果数

        Returns:
            AlibabaProduct 列表
        """
        results = []

        try:
            # 等待商品列表加载
            await page.wait_for_selector('.offer-item, [data-offerid]', timeout=10000)

            # 提取商品数据
            items = await page.query_selector_all('.offer-item, [data-offerid]')
            logger.info(f"找到 {len(items)} 个商品项")

            for item in items[:max_results]:
                try:
                    product = await self._extract_product_from_element(item)
                    if product:
                        results.append(product)
                except Exception as e:
                    logger.debug(f"提取商品失败: {e}")
                    continue

        except Exception as e:
            logger.error(f"解析浏览器结果失败: {e}")

        logger.info(f"成功解析 {len(results)} 个商品")
        return results

    async def _parse_html_results(
        self,
        html: str,
        keyword: str,
        max_results: int,
    ) -> List[PydanticAlibabaProduct]:
        """
        解析 HTML 搜索结果

        Args:
            html: HTML 内容
            keyword: 搜索关键词
            max_results: 最大结果数

        Returns:
            AlibabaProduct 列表
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'html.parser')
        results = []

        # 查找商品列表
        items = soup.select('.offer-item, [data-offerid]')
        logger.info(f"HTML 解析找到 {len(items)} 个商品项")

        for item in items[:max_results]:
            try:
                product = self._extract_product_from_soup(item)
                if product:
                    results.append(product)
            except Exception as e:
                logger.debug(f"提取商品失败: {e}")
                continue

        logger.info(f"HTML 解析成功 {len(results)} 个商品")
        return results

    async def _extract_product_from_element(self, element) -> Optional[PydanticAlibabaProduct]:
        """从浏览器元素提取商品信息"""
        try:
            # 提取标题
            title_elem = await element.query_selector('.title, .offer-title, a[title]')
            title = await title_elem.get_attribute('title') if title_elem else ""

            # 提取价格
            price_elem = await element.query_selector('.price, .offer-price')
            price_text = await price_elem.inner_text() if price_elem else "0"
            price = float(re.sub(r'[^\d.]', '', price_text) or 0)

            # 提取供应商
            supplier_elem = await element.query_selector('.company-name, .seller-name')
            supplier = await supplier_elem.inner_text() if supplier_elem else "Unknown"

            # 提取链接
            link_elem = await element.query_selector('a[href]')
            href = await link_elem.get_attribute('href') if link_elem else ""
            if href and not href.startswith('http'):
                href = f"https:{href}"

            # 提取商品ID
            item_id_match = re.search(r'/(\d+)\.html', href)
            item_id = item_id_match.group(1) if item_id_match else ""

            # 提取起订量
            moq_elem = await element.query_selector('.moq, .min-order')
            moq_text = await moq_elem.inner_text() if moq_elem else "1"
            moq_match = re.search(r'\d+', moq_text)
            moq = int(moq_match.group()) if moq_match else 1

            return PydanticAlibabaProduct(
                item_id=item_id,
                title=title.strip(),
                price=price,
                min_order_qty=moq,
                supplier=supplier.strip(),
                supplier_url="",
                product_url=href,
                location="",
            )

        except Exception as e:
            logger.debug(f"从元素提取商品失败: {e}")
            return None

    def _extract_product_from_soup(self, element) -> Optional[PydanticAlibabaProduct]:
        """从 BeautifulSoup 元素提取商品信息"""
        try:
            # 提取标题
            title_elem = element.select_one('.title, .offer-title, a[title]')
            title = title_elem.get('title', '') if title_elem else ""

            # 提取价格
            price_elem = element.select_one('.price, .offer-price')
            price_text = price_elem.get_text(strip=True) if price_elem else "0"
            price = float(re.sub(r'[^\d.]', '', price_text) or 0)

            # 提取供应商
            supplier_elem = element.select_one('.company-name, .seller-name')
            supplier = supplier_elem.get_text(strip=True) if supplier_elem else "Unknown"

            # 提取链接
            link_elem = element.select_one('a[href]')
            href = link_elem.get('href', '') if link_elem else ""
            if href and not href.startswith('http'):
                href = f"https:{href}"

            # 提取商品ID
            item_id_match = re.search(r'/(\d+)\.html', href)
            item_id = item_id_match.group(1) if item_id_match else ""

            # 提取起订量
            moq_elem = element.select_one('.moq, .min-order')
            moq_text = moq_elem.get_text(strip=True) if moq_elem else "1"
            moq_match = re.search(r'\d+', moq_text)
            moq = int(moq_match.group()) if moq_match else 1

            return PydanticAlibabaProduct(
                item_id=item_id,
                title=title.strip(),
                price=price,
                min_order_qty=moq,
                supplier=supplier.strip(),
                supplier_url="",
                product_url=href,
                location="",
            )

        except Exception as e:
            logger.debug(f"从 Soup 提取商品失败: {e}")
            return None

    @property
    def last_search_url(self) -> Optional[str]:
        """返回最后一次搜索的 URL"""
        return self._last_search_url
