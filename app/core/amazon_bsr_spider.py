# Amazon Pet Supplies BSR 榜单爬虫
# 目标：爬取 Pet Supplies 类目 Best Sellers Rank Top 100 商品数据
# 数据源：https://www.amazon.com/Best-Sellers-Pet-Supplies/zgbs/pet-supplies/ref=zg_bs_pet-supplies_home_all

import requests
from bs4 import BeautifulSoup
import json
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlparse
import re
import random

# 反爬虫工具
from app.utils.anti_block import UserAgentRotator, DelayManager, ProxyPool, retry_request, BlockDetector

# 渲染器（可选）
try:
    from app.utils.renderer import SyncRenderer, RenderConfig
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# 配置日志（必须在 PLAYWRIGHT_AVAILABLE 之后，以便 except 块可以使用 logger）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

if not PLAYWRIGHT_AVAILABLE:
    logger.warning("Playwright 未安装，渲染模式不可用")


@dataclass
class ProductInfo:
    """商品基础信息数据结构"""
    asin: str
    title: str
    brand: str
    category: str
    bsr: int  # Best Sellers Rank
    bsr_category: str  # BSR所属类目
    price: Optional[float]
    currency: str
    review_count: int
    rating: float
    seller_count: Optional[int]  # 独立卖家数（需二次统计）
    image_url: Optional[str]
    product_url: str
    fetched_at: str


class AmazonBSRSpider:
    """Amazon BSR 榜单爬虫（requests + BeautifulSoup 轻量实现）"""

    BASE_URL = "https://www.amazon.com"
    PET_SUPPLIES_ROOT = "/Best-Sellers-Pet-Supplies/zgbs/pet-supplies/"

    # Pet Supplies 常见子类目（后续可扩展配置化）
    SUBCATEGORIES = {
        "Dogs": "zg_bs_pet-supplies_home_all",
        "Cats": "zg_bs_pet-supplies_home_all",
        "Birds": "zg_bs_pet-supplies_home_all",
        "Fish & Aquatic Pets": "zg_bs_pet-supplies_home_all",
        "Reptiles & Amphibians": "zg_bs_pet-supplies_home_all",
    }



    def __init__(self, 
                 request_delay: tuple = (3, 8),
                 proxy: Optional[Dict] = None,
                 ua_rotator: Optional[UserAgentRotator] = None,
                 delay_manager: Optional[DelayManager] = None,
                 proxy_pool: Optional[ProxyPool] = None,
                 use_renderer: bool = False):
        """
        初始化爬虫（增强反爬虫 + 可选渲染器）
        
        Args:
            request_delay: 请求延迟范围 (min, max) 秒
            proxy: 单次代理配置
            ua_rotator/delay_manager/proxy_pool: 共享组件
            use_renderer: 是否启用 Playwright 渲染（对抗强反爬）
        """
        self.session = requests.Session()
        
        # 反爬虫组件
        self.ua_rotator = ua_rotator or UserAgentRotator()
        self.delay_manager = delay_manager or DelayManager(
            min_delay=request_delay[0], 
            max_delay=request_delay[1]
        )
        self.proxy_pool = proxy_pool
        self.single_proxy = proxy
        
        # 渲染器配置
        self.use_renderer = use_renderer and PLAYWRIGHT_AVAILABLE
        if use_renderer and not PLAYWRIGHT_AVAILABLE:
            logger.warning("启用渲染器但 Playwright 未安装，将降级为 requests 模式")
        
        self.renderer = None
        if self.use_renderer:
            try:
                self.renderer = SyncRenderer(RenderConfig(
                    headless=True,
                    browser_type="chromium",
                    timeout=30,
                    stealth_enabled=True,      # 启用 stealth
                    stealth_patch_all=True,    # 应用所有补丁
                    human_like=True,           # 人类化行为
                ))
                logger.info("✓ Playwright 渲染器已初始化（Stealth 模式）")
            except Exception as e:
                logger.error(f"渲染器初始化失败: {e}")
                self.use_renderer = False
        
        # 请求统计
        self.request_count = 0
        self.block_count = 0
        self.render_count = 0
        
        self.logger = logger
        
        # 确保输出目录存在
        import os
        os.makedirs("data/raw", exist_ok=True)
        os.makedirs("data/processed", exist_ok=True)
        os.makedirs("logs", exist_ok=True)
        logger.debug("✓ 输出目录已创建")

    def _extract_asin(self, url: str) -> Optional[str]:
        """从商品URL中提取ASIN"""
        # Amazon URL 格式: /dp/ASIN 或 /gp/product/ASIN
        patterns = [
            r'/dp/([A-Z0-9]{10})',
            r'/gp/product/([A-Z0-9]{10})',
            r'/product/([A-Z0-9]{10})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _parse_price(self, price_str: str) -> Optional[float]:
        """解析价格字符串为浮点数"""
        if not price_str:
            return None
        # 提取数字（处理 $19.99, ¥123 等格式）
        match = re.search(r'[\d,]+\.?\d*', price_str.replace(',', ''))
        if match:
            return float(match.group())
        return None

    def fetch_bsr_listing(self, category: str = "Dogs", page: int = 1) -> List[ProductInfo]:
        """
        获取单个类目的 BSR 榜单商品列表（增强反爬虫 + 渲染器回退）

        Args:
            category: 子类目名称
            page: 页码

        Returns:
            ProductInfo 列表
        """
        products = []
        url = f"{self.BASE_URL}{self.PET_SUPPLIES_ROOT}?pg={page}"

        self.logger.info(f"正在爬取: {category} - 第{page}页 - {url}")

        try:
            # === 步骤1: 尝试普通请求 ===
            self.delay_manager.wait()
            
            headers = {
                "User-Agent": self.ua_rotator.get(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
            }
            
            proxies = None
            if self.single_proxy:
                proxies = self.single_proxy
            elif self.proxy_pool and self.proxy_pool.proxies:
                proxy = self.proxy_pool.get()
                if proxy:
                    proxies = {"http": proxy, "https": proxy}
            
            response = None
            used_renderer = False
            
            # 重试循环（最多3次）
            for attempt in range(3):
                try:
                    response = self.session.get(
                        url, headers=headers, proxies=proxies, timeout=30,
                    )
                    response.raise_for_status()
                    break
                except requests.RequestException as e:
                    if attempt < 2:
                        wait = (attempt + 1) * 2 + random.uniform(0, 1)
                        self.logger.warning(f"请求失败，{wait:.1f}s后重试: {e}")
                        time.sleep(wait)
                        headers["User-Agent"] = self.ua_rotator.get()
                        if self.proxy_pool and proxies:
                            proxy = self.proxy_pool.get()
                            if proxy:
                                proxies = {"http": proxy, "https": proxy}
                    else:
                        raise
            
            self.request_count += 1
            
            # === 步骤2: 检测拦截 ===
            if response and BlockDetector.is_blocked(response.text, response.status_code):
                self.block_count += 1
                self.logger.warning(f"检测到拦截 (第{self.block_count}次)，状态码: {response.status_code}")
                self.logger.debug(f"  渲染器状态: use_renderer={self.use_renderer}, renderer={self.renderer is not None}")
                
                # 保存调试页面
                with open(f"data/raw/blocked_page{page}_{category}.html", "w", encoding="utf-8") as f:
                    f.write(response.text)
                
                # === 步骤3: 启用渲染器则切换模式 ===
                if self.use_renderer and self.renderer:
                    self.logger.info("🔄 切换到 Playwright 渲染模式重试...")
                    try:
                        self.logger.info(">>> 准备调用 _fetch_with_renderer")
                        html = self._fetch_with_renderer(url, category, page)
                        self.logger.info(f"<<< _fetch_with_renderer 返回: {type(html).__name__ if html else None}")
                        if html:
                            self.render_count += 1
                            return self._parse_page(html, category)
                        else:
                            self.logger.error("渲染模式返回空，失败")
                            return []
                    except Exception as e:
                        self.logger.error(f"渲染模式异常: {e}")
                        import traceback
                        self.logger.error(traceback.format_exc())
                        return []
                else:
                    self.logger.error("未启用渲染器，无法绕过拦截")
                    return []
            
            # === 步骤4: 正常解析 ===
            return self._parse_page(response.text, category)
            
        except requests.RequestException as e:
            self.logger.error(f"请求失败: {e}")
        except Exception as e:
            self.logger.error(f"未知错误: {e}", exc_info=True)
        
        return []
    

    def _fetch_with_requests(self, url: str, category: str, page: int) -> Optional[str]:
        """使用 requests + 反爬虫策略获取页面"""
        self.logger.info(f">>> 进入 _fetch_with_requests: page={page}")
        
        if not self.anti_block:
            self.logger.warning("反爬虫工具未初始化，跳过")
            return None
        
        try:
            # 应用反爬虫策略
            headers = self.anti_block.get_headers()
            proxies = self.anti_block.get_proxy()
            delay = self.anti_block.get_delay()
            
            time.sleep(delay)
            
            response = self.session.get(
                url,
                headers=headers,
                proxies=proxies,
                timeout=30,
                allow_redirects=True
            )
            
            html = response.text
            self.logger.info(f"✓ requests 成功: len={len(html)}")
            
            # 检测拦截
            blocked = BlockDetector.is_blocked(html, response.status_code)
            if blocked:
                self.logger.warning("requests 模式检测到拦截")
                filepath = f"data/raw/blocked_page{page}_{category}.html"
                import os
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(html)
                return None
            
            return html
            
        except Exception as e:
            self.logger.error(f"requests 失败: {e}")
            return None

    def _fetch_with_renderer(self, url: str, category: str, page: int) -> Optional[str]:
        """使用 Playwright 渲染页面"""
        self.logger.info(f">>> 进入 _fetch_with_renderer: page={page}")
        if not self.renderer:
            self.logger.warning("渲染器为 None，跳过")
            return None
        
        try:
            wait_for = "div[data-asin], div.zg_itemWrapper"
            self.logger.info(f"渲染页面: {url}")
            html = self.renderer.render(url, wait_for=wait_for, scroll_to_bottom=False)
            self.logger.info(f"渲染返回: type={type(html).__name__}, len={len(html) if html else 0}")
            
            if not html or len(html) < 10000:
                self.logger.warning("渲染结果过短或为空，可能失败")
                if html:
                    filepath = f"data/raw/blocked_render_{page}_{category}.html"
                    try:
                        import os
                        os.makedirs(os.path.dirname(filepath), exist_ok=True)
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(html)
                        self.logger.info(f"✓ 已保存拦截页面 ({len(html):,} 字节)")
                    except Exception as e:
                        self.logger.error(f"保存失败: {e}")
                return None
            
            blocked = BlockDetector.is_blocked(html, 200)
            self.logger.info(f"BlockDetector 结果: {blocked}")
            if blocked:
                self.logger.warning("渲染后检测到拦截关键词")
                filepath = f"data/raw/blocked_render_{page}_{category}.html"
                try:
                    import os
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(html)
                    self.logger.info(f"✓ 已保存拦截页面 ({len(html):,} 字节)")
                except Exception as e:
                    self.logger.error(f"保存失败: {e}")
                return None
            
            self.logger.info(f"✓ 渲染成功，长度: {len(html)}")
            return html
        except Exception as e:
            self.logger.error(f"渲染失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None

    
        """解析单个商品条目（BSR 页面专用）"""
        try:
            # 提取 ASIN
            asin = item.get('data-asin')
            if not asin:
                link = item.select_one('a[href*="/dp/"]')
                if link:
                    asin = self._extract_asin(link.get('href', ''))
            if not asin:
                return None
            
            # 提取标题
            title_elem = item.select_one('div.p13n-sc-truncate, div._cDEzb_p13n-sc-css-line-clamp-3_g3dy1, span.a-size-small.a-color-base')
            if not title_elem:
                title_elem = item.select_one('div[class*="Title"], span[class*="Title"]')
            title = title_elem.get_text(strip=True) if title_elem else ""
            
            # 提取品牌
            brand_elem = item.select_one('span.a-size-small.a-color-base')
            brand = brand_elem.get_text(strip=True) if brand_elem else ""
            
            # 提取价格
            price = self._parse_price(item)
            
            # 提取评分
            rating = None
            rating_elem = item.select_one('span.a-icon-alt')
            if rating_elem:
                import re
                match = re.search(r'([0-9.]+)\s*out\s*of\s*5', rating_elem.get_text())
                if match:
                    rating = float(match.group(1))
            
            # 提取评价数
            review_count = 0
            review_elem = item.select_one('span[class*="review"], a[href*="customerReviews"]')
            if review_elem:
                import re
                match = re.search(r'([0-9,]+)\s*review', review_elem.get_text(), re.IGNORECASE)
                if match:
                    review_count = int(match.group(1).replace(',', ''))
            
            # 构建商品 URL
            product_url = f"https://www.amazon.com/dp/{asin}"
            
        except Exception as e:
            self.logger.debug(f"解析商品失败: {e}")
            return None


    def _parse_product_item(self, item, category: str) -> Optional[ProductInfo]:
        """解析单个商品条目（BSR 页面专用）"""
        try:
            # 提取 ASIN
            asin = item.get("data-asin")
            if not asin:
                link = item.select_one("a[href*="/dp/"]")
                if link:
                    asin = self._extract_asin(link.get("href", ""))
            if not asin:
                return None

            # 提取标题
            title = ""
            for selector in ["h2", ".a-size-base-plus", ".a-size-medium", "._cDEzb_p13n-sc-css-line-clamp-3_g3dy1", "._cDEzb_p13n-sc-css-line-clamp-4_g3dy1"]:
                title_elem = item.select_one(selector)
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title:
                        break

            # 提取价格
            price = None
            for selector in ["span._cDEzb_p13n-sc-price_3mJ9Z", "span.a-price span.a-offscreen", ".a-price .a-offscreen"]:
                price_elem = item.select_one(selector)
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price = self._parse_price(price_text)
                    if price is not None:
                        break

            # 提取评分
            rating = None
            rating_elem = item.select_one("span.a-icon-alt")
            if rating_elem:
                try:
                    rating = float(rating_elem.get_text(strip=True).split()[0])
                except:
                    pass

            # 提取评论数
            review_count = 0
            for selector in ["span.a-size-small", ".a-size-small"]:
                review_elem = item.select_one(selector)
                if review_elem:
                    import re
                    text = review_elem.get_text(strip=True)
                    match = re.search(r"([\d,]+)\s*(?:ratings?|reviews?)", text, re.IGNORECASE)
                    if match:
                        review_count = int(match.group(1).replace(",", ""))
                        break

            # 构建 ProductInfo（字段对齐）
            from datetime import datetime
            product = ProductInfo(
                asin=asin,
                title=title or f"Amazon Product {asin}",
                brand="",
                category=category,
                bsr=0,
                bsr_category=category,
                price=price,
                currency="USD",
                review_count=review_count,
                rating=rating or 0.0,
                seller_count=None,
                image_url=None,
                product_url=f"{self.BASE_URL}/dp/{asin}",
                fetched_at=datetime.now().isoformat()
            )
            return product

        except Exception as e:
            self.logger.error(f"解析商品条目失败: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return None
    def _parse_page(self, html: str, category: str) -> List[ProductInfo]:
        """解析 HTML 页面（通用逻辑）"""
        products = []
        self.logger.info(f"_parse_page: HTML长度={len(html)}")
        soup = BeautifulSoup(html, 'html.parser')
        self.logger.info(f"BeautifulSoup 解析完成")
        
        item_selectors = [
            'div[data-asin]',
            'div.zg_itemWrapper',
            'div[data-component-type="s-search-result"]',
        ]
        
        items = []
        for selector in item_selectors:
            items = soup.select(selector)
            self.logger.info(f"选择器 '{selector}': 找到 {len(items)} 个商品")
            if items:
                break
        
        if not items:
            self.logger.warning(f"未找到商品列表")
            with open(f"data/raw/debug_{category}.html", "w", encoding="utf-8") as f:
                f.write(html)
            return []
        
        for item in items[:25]:
            try:
                product = self._parse_product_item(item, category)
                if product:
                    products.append(product)
            except Exception as e:
                self.logger.error(f"解析商品失败: {e}")
                continue
        
        self.logger.info(f"✓ 解析完成: {category} - {len(products)} 个商品")
        return products

if __name__ == "__main__":
    spider = AmazonBSRSpider(request_delay=(2, 5))

    print("开始爬取 Amazon Pet Supplies BSR Top 25...")
    result = spider.fetch_bsr_listing(category="Dogs", page=1)

    print(f"\n获取到 {len(result)} 个商品:")
    for i, p in enumerate(result[:5], 1):
        print(f"{i}. {p.title[:60]}")
        print(f"   ASIN: {p.asin} | BSR: #{p.bsr} | Price: ${p.price or 'N/A'} | Rating: {p.rating}")
        print(f"   Reviews: {p.review_count} | URL: {p.product_url[:60]}...")
        print()

    # 保存测试数据
    spider.save_to_json(result, "test_bsr_dogs_page1.json")
    print("✓ 测试完成，数据已保存到 data/raw/test_bsr_dogs_page1.json")
