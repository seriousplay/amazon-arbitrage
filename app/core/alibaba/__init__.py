"""
Alibaba Matcher Module

提供 1688 商品搜索和匹配功能

架构：
- browser.py: BrowserController - Playwright 生命周期管理
- captcha.py: CaptchaSolver - 4 层滑块破解策略
- search.py: SearchHandler - 1688 搜索和结果解析
- __init__.py: AlibabaMatcher facade - 对外统一接口
"""

from .browser import BrowserController
from .captcha import CaptchaSolver
from .search import SearchHandler
from .matcher import AlibabaMatcher

__all__ = ["AlibabaMatcher", "BrowserController", "CaptchaSolver", "SearchHandler"]
