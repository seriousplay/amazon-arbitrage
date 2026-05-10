"""
配置管理 - 使用 Pydantic Settings 管理环境变量
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    """应用配置"""

    # 应用基础配置
    APP_NAME: str = "Amazon Pet Arbitrage Scout"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", description="运行环境")
    DEBUG: bool = Field(default=False, description="调试模式")

    # API 配置
    API_HOST: str = Field(default="0.0.0.0", description="监听地址")
    API_PORT: int = Field(default=8000, description="监听端口")
    ALLOWED_ORIGINS: list = Field(default=["*"], description="CORS 允许的源")

    # 数据库配置
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///data/arbitrage.db",
        description="数据库连接字符串"
    )

    # Playwright 配置
    PLAYWRIGHT_HEADLESS: bool = Field(
        default=False,
        description="是否无头模式运行浏览器"
    )
    PLAYWRIGHT_TIMEOUT: int = Field(
        default=30000,
        description="页面加载超时（毫秒）"
    )
    BROWSER_CONCURRENCY: int = Field(
        default=2,
        description="浏览器并发数"
    )

    # 爬虫配置
    REQUEST_DELAY_MIN: float = Field(
        default=2.0,
        description="请求最小延迟（秒）"
    )
    REQUEST_DELAY_MAX: float = Field(
        default=5.0,
        description="请求最大延迟（秒）"
    )
    AMAZON_BSR_PAGES: int = Field(
        default=1,
        description="Amazon BSR 爬取页数"
    )
    ALIBABA_MAX_PAGES: int = Field(
        default=3,
        description="1688 搜索最大页数"
    )

    # 滑块破解配置
    SLIDER_MAX_RETRIES: int = Field(
        default=3,
        description="滑块破解最大重试次数"
    )
    SLIDER_USE_VISION: bool = Field(
        default=True,
        description="启用纯视觉检测"
    )
    CAPTCHA_DEBUG: bool = Field(
        default=True,
        description="保存调试截图"
    )

    # 评分配置
    MIN_SCORE_FOR_RECOMMENDATION: int = Field(
        default=60,
        description="推荐商品最低分数"
    )
    PRICE_DIFF_WEIGHT: float = Field(
        default=0.4,
        description="价差权重"
    )
    SALES_WEIGHT: float = Field(
        default=0.3,
        description="销量权重"
    )
    RATING_WEIGHT: float = Field(
        default=0.2,
        description="评分权重"
    )
    COMPETITION_WEIGHT: float = Field(
        default=0.1,
        description="竞争度权重"
    )

    # 并发控制
    MAX_WORKERS: int = Field(
        default=2,
        description="后台 worker 最大数量"
    )
    TASK_TIMEOUT: int = Field(
        default=600,
        description="任务超时（秒）"
    )

    # 路径配置
    DATA_DIR: str = Field(default="data", description="数据目录")
    COOKIES_DIR: str = Field(default="data/cookies", description="Cookies 目录")
    TEMP_DIR: str = Field(default="data/temp", description="临时文件目录")
    OUTPUT_DIR: str = Field(default="data/output", description="输出目录")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )


# 全局配置实例
settings = Settings()


def ensure_directories():
    """惰性创建必要目录（在应用启动时调用，避免导入时副作用）"""
    for dir_path in [
        settings.DATA_DIR,
        settings.COOKIES_DIR,
        settings.TEMP_DIR,
        settings.OUTPUT_DIR,
    ]:
        os.makedirs(dir_path, exist_ok=True)
