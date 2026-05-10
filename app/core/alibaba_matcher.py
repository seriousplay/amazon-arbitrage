"""
1688 匹配器 — Playwright 渲染搜索（基于已保存的 cookies）
"""

import asyncio
import json
import re
import time
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus

from app.models.product import AlibabaProduct as PydanticAlibabaProduct
from app.utils.logger import get_logger
from app.utils.translator import TERM_MAP, STOP_WORDS, to_chinese, translate_detail
from app.utils.category_mapper import category_to_search

logger = get_logger(__name__)

COOKIE_FILE = (
    Path(__file__).parent.parent.parent / "data" / "cookies" / "1688_cookies.json"
)


class AlibabaMatcher:
    """1688 匹配器 — Playwright 渲染页面，提取 JS 加载的商品数据"""

    def __init__(self, config):
        self.config = config
        self._has_cookies = COOKIE_FILE.exists()
        self._last_debug: dict = {}
        self._playwright = None
        self._browser = None

        if self._has_cookies:
            logger.info("✓ 1688 匹配器就绪（cookies 已找到）")
        else:
            logger.warning(
                f"⚠ 1688 cookies 未找到: {COOKIE_FILE}\n"
                "  运行 python scripts/save_1688_cookies.py 获取 cookies"
            )

    # ─── 公开 ─────────────────────────────────────────────

    @property
    def login_status(self) -> str:
        return "ok" if self._has_cookies else "needs_cookies"

    @property
    def cookies_file(self) -> str:
        return str(COOKIE_FILE)

    async def search_and_match(
        self, keyword: str, category: str = None, category_path: str = None
    ) -> List[PydanticAlibabaProduct]:
        if not self._has_cookies:
            return []

        try:
            return await self._do_search(keyword, category, category_path)
        except Exception as e:
            logger.error(f"search_and_match 异常: {e}")
            self._last_debug = {"error": str(e)}
            return []

    async def _do_search(
        self, keyword: str, category: str = None, category_path: str = None
    ) -> List[PydanticAlibabaProduct]:
        # 提取品牌名
        words = keyword.split()
        brand = ""
        if words and words[0][0].isupper() and len(words[0]) >= 3:
            brand = words[0].strip("'\",-.")

        # 方式 A：Amazon 类目映射（精准，无翻译）
        exact_cat = category_to_search(category_path or "") if category_path else ""
        if exact_cat:
            logger.info(f"🔍 1688 搜索(类目): '{keyword[:40]}...' → '{exact_cat}'")

            # 搜索词：品牌 + 类目映射词
            term = f"{brand} {exact_cat}".strip() if brand else exact_cat
            result = await self._search(term)
            if result:
                return self._filter_relevance(keyword, result)
            # 不加品牌再试一次
            if brand:
                result = await self._search(exact_cat)
                if result:
                    return self._filter_relevance(keyword, result)
            # 类目映射无结果，返回空（不降级到翻译）
            logger.info(f"  类目映射 '{exact_cat}' 无结果")
            return []

        # 方式 B：无类目路径时，用翻译（仅回退）
        cn = to_chinese(keyword)
        logger.info(f"🔍 1688 搜索(翻译): '{keyword[:40]}...' → '{cn}'")
        cat_kw = self._category_keyword(category) if category else ""

        search_terms = []
        if brand and cn:
            search_terms.append(f"{brand} {cn}")
        if cat_kw and cn:
            search_terms.append(f"{cat_kw} {cn}")
        if cn:
            search_terms.append(cn)

        for term in search_terms[:2]:
            result = await self._search(term)
            if result:
                return self._filter_relevance(keyword, result)

        # 最后一搏：英文原文
        if cn and cn != keyword:
            result = await self._search(keyword)
            if result:
                return self._filter_relevance(keyword, result)
        return []

    def translate_keyword(self, title: str) -> dict:
        return translate_detail(title)

    # ─── 品类关键词映射 ──────────────────────────────────

    CATEGORY_KEYWORDS = {
        "pet supplies": "宠物用品",
        "electronics": "电子产品",
        "home & kitchen": "家居厨房",
        "toys & games": "玩具",
        "sports & outdoors": "运动户外",
        "beauty & personal care": "美容护理",
        "health & household": "健康家居",
        "baby products": "婴儿用品",
        "office products": "办公文具",
        "garden & outdoor": "花园户外",
        "tools & home improvement": "工具家装",
        "automotive": "汽车用品",
        "clothing & shoes": "服装鞋帽",
        "clothing": "服装",
        "books": "图书",
        "kitchen & dining": "厨房餐厅",
        "video games": "游戏",
        "musical instruments": "乐器",
        "industrial & scientific": "工业科学",
        "arts & crafts": "手工艺术",
        "arts crafts": "手工艺术",
        "grocery & gourmet food": "食品",
        "grocery": "食品",
    }

    @staticmethod
    def _category_keyword(category: str) -> str:
        """Amazon 类目 → 1688 搜索用中文品类词"""
        if not category:
            return ""
        key = category.lower().strip()
        for k, v in AlibabaMatcher.CATEGORY_KEYWORDS.items():
            if k in key or key in k:
                return v
        return ""

    def _filter_relevance(
        self, amazon_title: str, ali_products: List[PydanticAlibabaProduct]
    ) -> List[PydanticAlibabaProduct]:
        """基于中文关键词重叠度过滤不相关的 1688 商品"""
        import re as _re

        # 提取 Amazon 标题中的英文关键词并翻译为中文
        title_lower = amazon_title.lower()
        words = _re.findall(r"[a-z0-9]+", _re.sub(r"[^\w\s]", " ", title_lower))
        en_keywords = [w for w in words if len(w) >= 2 and w not in STOP_WORDS][:8]

        # 翻译为中文关键词集合
        cn_keywords = set()
        for kw in en_keywords:
            if kw in TERM_MAP:
                cn_keywords.add(TERM_MAP[kw])

        if not cn_keywords or len(cn_keywords) <= 1:
            # 关键词太少，不过滤
            return ali_products[:5]

        # 对每个 1688 商品计算相关性分
        scored = []
        for p in ali_products:
            ali_title = p.title.lower()
            matched = sum(1 for cn in cn_keywords if cn in ali_title)
            relevance = matched / len(cn_keywords)

            # 放宽条件：至少匹配 1 个，或关键词只有 2 个时匹配 0 个也放行
            min_match = 1 if len(cn_keywords) >= 3 else 0
            if matched >= min_match:
                p.matched_score = max(relevance * 100.0, 20.0)  # 最低 20 分
                scored.append((relevance, p))
            else:
                logger.debug(f"  过滤: '{p.title[:40]}...' ({matched}/{len(cn_keywords)} 匹配)")

        # 按相关度排序，取前 5
        scored.sort(key=lambda x: x[0], reverse=True)
        result = [p for _, p in scored[:5]]

        # 如果全部被过滤且有足够关键词，不返回无关结果
        if not result and ali_products and len(cn_keywords) < 3:
            # 只有关键词很少时才回退（避免返回完全不相关的商品）
            for p in ali_products[:3]:
                p.matched_score = 10.0
                result.append(p)

        if result and len(result) < len(ali_products):
            logger.info(
                f"  相关性过滤: {len(ali_products)} → {len(result)} "
                f"(关键词: {cn_keywords})"
            )

        return result

    # ─── 搜索核心 ─────────────────────────────────────────

    async def _search(self, keyword: str) -> List[PydanticAlibabaProduct]:
        """Playwright 渲染 1688 移动端搜索页并提取商品数据"""
        encoded = quote_plus(keyword)
        # 移动端搜索，反爬保护比 PC 端轻
        url = f"https://m.1688.com/offer_search/-{encoded}.html?keywords={encoded}"

        self._last_debug = {"keyword": keyword, "url": url}

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright 未安装: pip install playwright && playwright install chromium")
            return []

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-infobars",
                        "--disable-dev-shm-usage",
                    ],
                )
                context = await browser.new_context(
                    viewport={"width": 1440, "height": 900},
                    locale="zh-CN",
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                )

                # 加载 cookies
                cookies = json.loads(COOKIE_FILE.read_text())
                if isinstance(cookies, list):
                    await context.add_cookies(cookies)

                page = await context.new_page()

                # 隐藏 webdriver 痕迹
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
                    window.chrome = {runtime: {}};
                """)

                self._last_debug["status"] = "navigating"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                # 等待搜索结果加载
                await asyncio.sleep(4)

                # 诊断：页面基本信息
                diag = await page.evaluate("""() => ({
                    title: document.title,
                    offerIdCount: document.querySelectorAll('[data-offer-id]').length,
                    offerLinks: document.querySelectorAll('a[href*="offer"]').length,
                    bodyLen: document.body ? document.body.innerText.length : 0,
                    hasPrice: (document.body ? document.body.innerText : '').includes('¥'),
                })""")
                self._last_debug["page_diag"] = diag

                # 检测验证码
                if "验证码" in (diag.get("title") or ""):
                    self._last_debug["blocked"] = "验证码拦截"
                    logger.warning("1688 触发验证码，请稍后重试或更换 IP")
                    await browser.close()
                    return []

                # 在页面中执行 JS 提取商品数据
                raw_data = await page.evaluate("""() => {
                    const results = [], seen = new Set();
                    const els = document.querySelectorAll(
                        'a[href*="/offer/"], [data-offer-id], a[href*="offerId"]'
                    );
                    els.forEach(el => {
                        // 提取 offerId
                        let oid = el.getAttribute('data-offer-id') || '';
                        if (!oid) {
                            const h = el.href || el.getAttribute('href') || '';
                            const m = h.match(/offer[\\/](\\d+)/) || h.match(/offerId[=:](\\d+)/);
                            if (m) oid = m[1];
                        }
                        if (!oid || seen.has(oid)) return;

                        // 找父容器（向上查找，直到遇到包含 ¥ 且有意义的容器）
                        let card = el;
                        for (let i=0; i<5; i++) {
                            card = card.parentElement;
                            if (!card) break;
                            const t = (card.innerText||'').trim();
                            if (t.length > 40 && /[¥￥]/.test(t)) break;
                        }
                        const fullText = (card.innerText||'').trim();
                        if (fullText.length < 25) return;
                        if (/交流|聊天|语音|扫码|下载APP|导航|分类/.test(fullText)) return;

                        // 从容器内专门的 price 元素提取价格，而非全文匹配
                        let price = 0;
                        const priceEl = card.querySelector('[class*="price"], [class*="Price"], span[class*="num"], em');
                        const priceText = priceEl ? priceEl.innerText : fullText;
                        const pm = priceText.match(/[¥￥]\\s*([\\d,.]+)/);
                        if (pm) price = parseFloat(pm[1].replace(/,/g, ''));

                        // 如果从 price 元素没找到，尝试全文匹配第二个 ¥（第一个可能是广告标签）
                        if (!price) {
                            const allPM = [...fullText.matchAll(/[¥￥]\\s*([\\d,.]+)/g)];
                            if (allPM.length >= 2) price = parseFloat(allPM[1][1].replace(/,/g, ''));
                            else if (allPM.length === 1) price = parseFloat(allPM[0][1].replace(/,/g, ''));
                        }
                        if (!price || price <= 0) return;

                        let title = el.getAttribute('title') || el.innerText || '';
                        title = title.split(/[\\n¥￥]/)[0].trim();
                        if (!title || title.length < 4) return;

                        seen.add(oid);
                        results.push({
                            offerId: oid,
                            title: title.substring(0, 200),
                            price: price,
                            moqText: (fullText.match(/[≥>=]\\s*(\\d+)\\s*[件个]/)||['','2'])[1],
                            supplier: ((card.querySelector('[class*="supplier"], [class*="company"], [class*="shop"]')||{}).innerText||''),
                        });
                    });
                    return results;
                }""")

                await browser.close()

                # 转换 JS 提取的数据
                products = []
                seen = set()
                for item in (raw_data or [])[:10]:
                    oid = str(item.get("offerId", ""))
                    if oid in seen:
                        continue
                    seen.add(oid)
                    title = item.get("title", "")
                    price = float(item.get("price", 0))
                    if not title or price <= 0:
                        continue
                    moq = int(item.get("moqText", 2) or 2)
                    supplier = item.get("supplier", "") or "1688供应商"
                    # 清理标题中残留的非商品文本
                    title = re.sub(r"元宝.*|先采后付|回头率.*|退货.*|运费.*|\\+件.*", "", title).strip()
                    products.append(PydanticAlibabaProduct(
                        item_id=oid, title=title[:200], price=price,
                        min_order_qty=max(2, moq),
                        supplier=supplier[:100] if supplier else "1688供应商",
                        item_url=f"https://detail.1688.com/offer/{oid}.html",
                        matched_score=50.0,
                    ))

                self._last_debug["found"] = len(products)

                self._last_debug["found"] = len(products)
                self._last_debug["raw_count"] = len(raw_data or [])
                logger.info(f"✓ 1688 搜索: {len(products)} 个结果")
                self._last_debug["found"] = len(products)
                logger.info(f"✓ 1688 搜索: {len(products)} 个结果")
                return products

        except Exception as e:
            import traceback
            self._last_debug["error"] = str(e)
            self._last_debug["traceback"] = traceback.format_exc()[-500:]
            logger.error(f"1688 搜索异常: {e}\n{traceback.format_exc()}")

            # ── Playwright 失败，回退到 HTTP 直连搜索 ──
            fallback = await self._search_http(keyword)
            if fallback:
                logger.info(f"✓ HTTP 回退搜索成功: {len(fallback)} 个结果")
                self._last_debug["fallback"] = f"http:{len(fallback)}"
                return fallback
            logger.warning(f"HTTP 回退搜索也失败: {keyword[:40]}")
            return []

    async def _search_http(self, keyword: str) -> List[PydanticAlibabaProduct]:
        """HTTP 直连搜索 1688 — Playwright 超时时备用

        直接请求 m.1688.com 移动端搜索页，用 BeautifulSoup 解析 SSR HTML。
        不需要启动浏览器，速度快且更稳定。
        """
        import httpx
        from bs4 import BeautifulSoup

        encoded = quote_plus(keyword)
        url = f"https://m.1688.com/offer_search/-{encoded}.html?keywords={encoded}"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://m.1688.com/",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
        }

        self._last_debug["http_fallback_url"] = url

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            self._last_debug["http_status"] = resp.status_code
            logger.warning(f"HTTP 回退返回 {resp.status_code}: {keyword[:40]}")
            return []

        # 用现有的 _parse 方法从 HTML 中提取商品
        return self._parse(resp.text, keyword)

    # ─── 解析 ─────────────────────────────────────────────

    def _parse(self, html: str, keyword: str) -> List[PydanticAlibabaProduct]:
        """从渲染后的 HTML 提取商品数据"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        # 方式 1: 从 script 标签提取 JSON
        products = self._parse_scripts(html)
        if products:
            return products

        # 方式 2: 直接解析 HTML 元素
        return self._parse_html(soup)

    def _parse_scripts(self, html: str) -> List[PydanticAlibabaProduct]:
        """从 <script> 中提取内嵌的 JSON 商品数据"""
        # 提取所有 script 标签内容
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        for script in scripts:
            if not script.strip():
                continue
            # 搜索包含 offerId 或 price 的 JSON
            for match in re.finditer(r"\{[^}]*\"offerId\"[^}]*\}", script):
                try:
                    data = json.loads(match.group())
                    if data.get("offerId"):
                        result = self._convert([data])
                        if result:
                            return result
                except json.JSONDecodeError:
                    continue

        # 宽泛模式：搜索任何包含商品字段的 JSON 对象/数组
        patterns = [
            r'"offers"\s*:\s*(\[.+?\])',
            r'"offerList"\s*:\s*(\[.+?\])',
            r'"items"\s*:\s*(\[.+?\])',
            r'"result"\s*:\s*(\[.+?\])',
            r'window\.__DATA__\s*=\s*(\{.+?\});',
            r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\});',
            r'__NEXT_DATA__\s*=\s*(\{.+?\});',
        ]
        for pat in patterns:
            for match in re.finditer(pat, html, re.DOTALL):
                json_str = match.group(1) if match.lastindex else match.group(0)
                try:
                    data = json.loads(json_str)
                    offers = self._find_list(data)
                    if offers:
                        return self._convert(offers)
                except (json.JSONDecodeError, Exception):
                    continue

        # 最后手段：在整页 HTML 中搜索任何 offer 链接
        offer_links = re.findall(r'href="(https?://detail\.1688\.com/offer/\d+\.html)"', html)
        if offer_links:
            # 尝试从附近的文本提取
            return self._parse_from_links(html, offer_links)
        return []

    def _parse_from_links(self, html: str, links: list) -> List[PydanticAlibabaProduct]:
        """从 offerId 参数或 offer 链接提取商品"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        results = []
        seen_ids = set()

        # 从 URL 参数中提取 offerId
        offer_ids = re.findall(r'offerId[=:]\s*["\']?(\d+)', html)
        for oid in offer_ids[:20]:
            if oid in seen_ids:
                continue
            seen_ids.add(oid)

            # 在 HTML 中找到包含此 offerId 的容器
            container = soup.find(attrs={"data-offer-id": oid})
            if not container:
                # 搜索包含此 offerId 的任何元素
                for el in soup.select(f"[href*='{oid}'], [data-id*='{oid}']"):
                    container = el
                    for _ in range(5):
                        container = container.parent
                        if container and len(container.get_text(strip=True)) > 30:
                            break
                    break

            if not container:
                continue

            text = container.get_text(strip=True)

            # 过滤非商品
            skip = ["交流", "聊天", "语音", "视频", "扫码", "下载", "导航", "分类", "筛选"]
            if any(w in text for w in skip):
                continue

            # 标题
            title = ""
            for el in container.select("a[title], h3, .title, [class*='title'], [class*='subject']"):
                t = el.get("title") or el.get_text(strip=True)
                if len(t) > len(title) and len(t) >= 4:
                    title = t
            if not title:
                continue

            # 价格
            price = 0.0
            pm = re.search(r"[¥￥]\s*([\d,.]+)", text)
            if pm:
                price = float(pm.group(1).replace(",", ""))
            if price <= 0:
                continue

            # 供应商
            supplier = "1688供应商"
            sup_el = container.select_one("[class*='supplier'], [class*='company'], [class*='shop']")
            if sup_el:
                supplier = sup_el.get_text(strip=True)[:100]

            # MOQ
            moq = 2
            moq_m = re.search(r"[≥>=]\s*(\d+)", text) or re.search(r"(\d+)\s*[件个起]", text)
            if moq_m:
                moq = int(moq_m.group(1))

            results.append(PydanticAlibabaProduct(
                item_id=oid, title=title[:200], price=price,
                min_order_qty=max(2, moq), supplier=supplier,
                item_url=f"https://detail.1688.com/offer/{oid}.html",
                matched_score=50.0,
            ))

        return results

    def _find_list(self, obj, depth=0):
        """递归查找包含 offerId/subject 的商品列表"""
        if depth > 8:
            return None
        if isinstance(obj, list) and len(obj) > 0 and isinstance(obj[0], dict):
            if any(k in obj[0] for k in ("offerId", "subject", "title", "price")):
                return obj
            for item in obj:
                r = self._find_list(item, depth + 1)
                if r:
                    return r
        elif isinstance(obj, dict):
            for k, v in obj.items():
                r = self._find_list(v, depth + 1)
                if r:
                    return r
        return None

    def _parse_html(self, soup) -> List[PydanticAlibabaProduct]:
        """从渲染后 HTML 提取商品"""
        # 1688 搜索结果的标准容器
        items = soup.select(
            "div[class*='offer-item'], div.offer_item, div.sm-offer-item, "
            "div[class*='OfferItem'], li[class*='offer'], "
            "div[class*='list--'] > div[class*='item']"
        )
        if not items:
            # 宽泛回退：找含价格、标题链接的容器
            items = [d for d in soup.select("div, li")
                     if d.select_one("a[href*='offer']") and "¥" in d.get_text()]

        results = []
        seen_titles = set()
        for item in items[:15]:
            try:
                text = item.get_text(strip=True)

                # 过滤非商品（聊天窗口、广告、导航等）
                skip_words = ["交流", "聊天", "语音", "视频", "扫码", "下载APP",
                              "导航", "分类", "筛选", "排序"]
                if any(w in text for w in skip_words):
                    continue

                # 提取价格
                price = 0.0
                price_el = item.select_one(
                    "span[class*='price'], div[class*='price'], "
                    "span[class*='Price'], em[class*='price']"
                )
                if price_el:
                    price_text = price_el.get_text(strip=True)
                else:
                    price_text = text
                pm = re.search(r"[¥￥]\s*([\d,.]+)", price_text)
                if pm:
                    price = float(pm.group(1).replace(",", ""))
                if price <= 0:
                    continue

                # 提取标题
                title = ""
                for sel in ["a[title]", "a.offer-title", "h3", "a[class*='title']",
                            "a[class*='Title']", ".offer-title", "[class*='title']"]:
                    el = item.select_one(sel)
                    if el:
                        t = el.get("title") or el.get_text(strip=True)
                        t = re.sub(r"\s+", " ", t).strip()
                        if len(t) > len(title) and len(t) >= 4:
                            title = t
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                # 供应商
                supplier = "1688供应商"
                sup_el = item.select_one(
                    "a[class*='supplier'], a[class*='company'], "
                    "span[class*='supplier'], .company-name"
                )
                if sup_el:
                    supplier = sup_el.get_text(strip=True)[:100]

                # 链接
                link = item.select_one("a[href*='offer']")
                offer_url = "https:" + link["href"] if link and link.get("href") else ""
                pid = ""
                if offer_url:
                    m = re.search(r"offer/(\d+)", offer_url)
                    if m:
                        pid = m.group(1)

                # MOQ
                moq = 2
                moq_m = re.search(r"[≥>=]\s*(\d+)", text) or re.search(r"(\d+)\s*[件个起]", text)
                if moq_m:
                    moq = int(moq_m.group(1))

                results.append(PydanticAlibabaProduct(
                    item_id=pid or f"pw_{abs(hash(title)) % 10**9:09d}",
                    title=title[:200], price=price,
                    min_order_qty=max(2, moq),
                    supplier=supplier, item_url=offer_url or None,
                    matched_score=50.0,
                ))
            except Exception:
                continue
        return results

    def _convert(self, offers: list) -> List[PydanticAlibabaProduct]:
        products = []
        for o in offers[:10]:
            if not isinstance(o, dict):
                continue
            try:
                title = o.get("subject") or o.get("title") or o.get("offerName") or ""
                if not title:
                    continue
                price = 0.0
                pr = o.get("price") or o.get("offerPrice") or o.get("tradePrice") or 0
                if isinstance(pr, (int, float)):
                    price = float(pr)
                elif isinstance(pr, str):
                    nums = re.findall(r"[\d.]+", str(pr))
                    price = float(nums[0]) if nums else 0.0
                if price <= 0:
                    continue
                moq = o.get("minOrderQuantity") or o.get("beginQuantity") or 2
                if isinstance(moq, str):
                    moq = int(re.sub(r"\D", "", moq) or 2)
                products.append(PydanticAlibabaProduct(
                    item_id=str(o.get("offerId", "")),
                    title=title[:200], price=price,
                    min_order_qty=max(2, int(moq)),
                    supplier=str(o.get("companyName") or "1688供应商")[:100],
                    matched_score=50.0,
                ))
            except Exception:
                continue
        return products

    async def match_amazon_product(
        self,
        asin: str,
        title: str,
        category: str,
        price: float = None,
        max_results: int = 3
    ) -> Optional[PydanticAlibabaProduct]:
        """
        匹配单个 Amazon 商品到 1688 最优供应商
        
        对应原技能 AlibabaMatcherFull.match_amazon_product 的简化接口
        """
        if not self._has_cookies:
            return None
        
        try:
            # 调用 search_and_match 获取候选列表
            products = await self.search_and_match(
                keyword=title,
                category=category,
                category_path=category
            )
            
            if not products:
                return None
            
            # 返回评分最高的一个（match_and_match 已按相关性排序）
            return products[0] if products else None
            
        except Exception as e:
            logger.error(f"match_amazon_product 失败 ({asin}): {e}")
            return None


    async def cleanup(self):
        pass
