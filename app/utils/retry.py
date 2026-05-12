"""
重试装饰器与错误恢复机制
对网络请求进行指数退避重试
"""

import time
import logging
import random
from functools import wraps
from typing import Callable, TypeVar, Any
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (RequestException, ConnectionError, TimeoutError),
):
    """
    指数退避重试装饰器

    Args:
        max_attempts: 最大重试次数（含首次）
        initial_delay: 初始延迟（秒）
        max_delay: 最大延迟
        backoff_factor: 退避倍数
        exceptions: 捕获的异常类型
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            delay = initial_delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    logger.debug(f"执行 {func.__name__} (尝试 {attempt}/{max_attempts})")
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(f"❌ {func.__name__} 最终失败: {e}")
                        raise

                    # 指数退避 + 随机抖动（±20%）
                    jitter = random.uniform(0.8, 1.2)
                    sleep_time = min(delay * jitter, max_delay)
                    logger.warning(f"⚠️  {func.__name__} 失败，{sleep_time:.1f}s后重试: {e}")
                    time.sleep(sleep_time)
                    delay *= backoff_factor

            raise last_exception  # type: ignore

        return wrapper

    return decorator


# 使用示例
if __name__ == "__main__":
    import requests

    @retry(max_attempts=4, initial_delay=0.5)
    def fetch_url(url: str) -> str:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text

    # 测试重试（使用一个不稳定的测试URL）
    # print(fetch_url("https://httpbin.org/status/500"))
