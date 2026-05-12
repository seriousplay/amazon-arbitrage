"""
pytest 共享 fixtures
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_config():
    c = MagicMock()
    c.APP_NAME = "Test App"
    c.VERSION = "1.0.0"
    c.ENVIRONMENT = "test"
    c.DATABASE_URL = "sqlite+aiosqlite:///data/test.db"
    c.ALLOWED_ORIGINS = ["*"]
    c.MAX_WORKERS = 1
    c.TASK_TIMEOUT = 600
    c.AMAZON_BSR_PAGES = 1
    c.ALIBABA_MAX_PAGES = 1
    c.REQUEST_DELAY_MIN = 0.1
    c.REQUEST_DELAY_MAX = 0.5
    c.PLAYWRIGHT_HEADLESS = True
    c.PRICE_DIFF_WEIGHT = 0.4
    c.SALES_WEIGHT = 0.3
    c.RATING_WEIGHT = 0.2
    c.COMPETITION_WEIGHT = 0.1
    c.DEBUG = False
    c.CAPTCHA_DEBUG = False
    c.DEFAULT_MATCH_CONCURRENCY = 3
    c.DEFAULT_MATCH_TIMEOUT = 90
    c.CAPTCHA_CONFIDENCE_THRESHOLD = 0.8
    return c


@pytest.fixture
def mock_storage():
    s = MagicMock()
    s.initialize = AsyncMock()
    s.save_scan_task = AsyncMock()
    s.get_task = AsyncMock(return_value=None)
    s.list_recent_tasks = AsyncMock(return_value=[])
    s.close = AsyncMock()
    s.is_connected = True
    return s
