"""
UPC/EAN 码查询服务
通过公开 API 查询商品条码对应的商品信息
用于 Amazon-1688 精准匹配
"""

import requests
import logging
from typing import Optional, Dict
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


class UPCLookup:
    """UPC 码查询（公开 API 免费版）"""

    # 公开 API 端点（有限次数）
    PUBLIC_APIS = [
        "https://api.upcitemdb.com/prod/trial/lookup?upc={upc}",
        "https://api.barcodelookup.com/v3/products?barcode={upc}&formatted=y&key=test",  # 测试key
    ]

    # 备选：通过 Google Shopping 搜索（需代理）
    GOOGLE_SHOPPING_URL = "https://shopping.google.com/search?q={upc}"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }

    def __init__(self, api_key: Optional[str] = None, proxy: Optional[Dict] = None):
        """
        初始化 UPC 查询

        Args:
            api_key: UPCItemDB API key（付费版可提高限额）
            proxy: 代理配置
        """
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        if proxy:
            self.session.proxies.update(proxy)

    def lookup(self, upc: str) -> Optional[Dict]:
        """
        查询 UPC 码

        Args:
            upc: 12位 UPC 码（或 13位 EAN）

        Returns:
            商品信息字典（标题、品牌、图片等），未找到返回 None
        """
        upc = upc.strip()
        if not self._validate_upc(upc):
            logger.warning(f"无效的UPC码: {upc}")
            return None

        # 尝试公开 API
        url = f"https://api.upcitemdb.com/prod/trial/lookup?upc={upc}"

        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") == "OK" and data.get("total") > 0:
                item = data["items"][0]
                result = {
                    "upc": upc,
                    "title": item.get("title", ""),
                    "brand": item.get("brand", ""),
                    "category": item.get("category", ""),
                    "images": item.get("images", []),
                    "description": item.get("description", ""),
                    "source": "upcitemdb",
                }
                logger.info(f"✓ UPC查询成功: {upc} → {result['title'][:50]}")
                return result
            else:
                logger.debug(f"UPC未找到: {upc}")
                return None

        except requests.RequestException as e:
            logger.error(f"UPC API请求失败: {e}")
            return None

    def _validate_upc(self, upc: str) -> bool:
        """验证 UPC 码格式（12位数字，含校验位）"""
        clean = "".join(filter(str.isdigit, upc))
        if len(clean) not in (12, 13):
            return False

        # 可选：校验位验证（Luhn算法变体）
        # 简化版：只检查长度和数字
        return True

    def extract_upc_from_amazon(self, html: str) -> Optional[str]:
        """
        从 Amazon 商品页 HTML 中提取 UPC/EAN

        位置：
        - 商品详情页的 "Item model number" 字段
        - URL 中的 /dp/ASIN 并非 UPC
        - 有时在 <span class="a-text-bold">UPC</span> 相邻节点
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # 查找 UPC 标签
        upc_labels = soup.find_all(string=re.compile(r"UPC|EAN|Item model number", re.I))
        for label in upc_labels:
            parent = label.parent
            if parent:
                # 提取相邻的数值
                sibling = parent.find_next_sibling()
                if sibling:
                    text = sibling.get_text(strip=True)
                    if re.match(r"^\d{12,13}$", text):
                        logger.info(f"✓ 提取UPC: {text}")
                        return text

        return None


# 测试
if __name__ == "__main__":
    lookup = UPCLookup()

    # 测试商品 UPC（常见宠物用品）
    test_upcs = [
        "123456789012",  # 虚假
        "853741003036",  # 示例（可能不存在）
    ]

    for upc in test_upcs:
        print(f"\n查询: {upc}")
        result = lookup.lookup(upc)
        if result:
            print(f"  标题: {result['title']}")
            print(f"  品牌: {result['brand']}")
        else:
            print("  未找到")
