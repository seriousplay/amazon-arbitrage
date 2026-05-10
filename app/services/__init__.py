"""服务层包"""
from .storage import StorageService

# BrowserPool 和 CaptchaSolver 暂未实现
# __all__ = ["StorageService", "BrowserPool", "CaptchaSolver"]
__all__ = ["StorageService"]
