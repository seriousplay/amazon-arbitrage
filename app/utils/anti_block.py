#!/usr/bin/env python3
"""
反爬虫策略工具包
提供：User-Agent轮换、请求延迟、代理池、异常重试
"""

import time
import random
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ========== 数据类 ==========


@dataclass
class RequestConfig:
    """请求配置"""

    user_agent: str
    delay_min: float = 2.0
    delay_max: float = 5.0
    proxy: Optional[str] = None
    timeout: int = 30
    retry_times: int = 3


# ========== User-Agent 轮换器 ==========


class UserAgentRotator:
    """User-Agent 轮换器"""

    def __init__(self, agents: Optional[List[str]] = None):
        self.agents = agents or self._default_agents()
        self.index = 0

    def _default_agents(self) -> List[str]:
        """默认 User-Agent 池（Chrome/Windows/macOS）"""
        return [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        ]

    def get(self) -> str:
        """获取下一个 User-Agent"""
        ua = self.agents[self.index % len(self.agents)]
        self.index += 1
        return ua

    def random(self) -> str:
        """随机获取一个 User-Agent"""
        return random.choice(self.agents)


# ========== 请求延迟控制 ==========


class DelayManager:
    """请求延迟管理器（随机化防止检测）"""

    def __init__(self, min_delay: float = 2.0, max_delay: float = 5.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.last_request_time = 0

    def wait(self, jitter: float = 0.5) -> None:
        """
        等待随机间隔
        jitter: 额外抖动（秒）
        """
        now = time.time()
        elapsed = now - self.last_request_time

        # 计算目标等待时间（区间随机 + 抖动）
        target_delay = random.uniform(self.min_delay, self.max_delay) + jitter

        # 如果距离上次请求时间不足，则补足延迟
        if elapsed < target_delay:
            sleep_time = target_delay - elapsed
            logger.debug(
                f"Delay: 等待 {sleep_time:.2f}s (最小 {self.min_delay}s, 最大 {self.max_delay}s)"
            )
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def reset(self) -> None:
        """重置计时器（用于域名切换）"""
        self.last_request_time = 0


# ========== 代理池管理器 ==========


class ProxyPool:
    """简单代理池（支持轮换和健康检查）"""

    def __init__(self, proxies: List[str] = None):
        self.proxies = proxies or []
        self.bad_proxies = set()  # 标记为不可用的代理
        self.current_index = 0

    def get(self) -> Optional[str]:
        """获取下一个可用代理"""
        if not self.proxies:
            return None

        # 循环查找可用代理
        for _ in range(len(self.proxies)):
            proxy = self.proxies[self.current_index % len(self.proxies)]
            self.current_index += 1
            if proxy not in self.bad_proxies:
                return proxy

        # 所有代理均不可用
        logger.warning("代理池中无可用代理")
        return None

    def mark_bad(self, proxy: str) -> None:
        """标记代理失效"""
        self.bad_proxies.add(proxy)
        logger.info(f"代理标记为失效: {proxy}")

    def reset(self) -> None:
        """重置代理池状态（用于重新尝试）"""
        self.bad_proxies.clear()
        self.current_index = 0


# ========== 重试装饰器 ==========


def retry_request(max_retries: int = 3, retry_codes: List[int] = None, backoff_factor: float = 1.0):
    """
    请求重试装饰器

    Args:
        max_retries: 最大重试次数
        retry_codes: 需要重试的HTTP状态码（默认：503, 504, 522, 524, 408, 429）
        backoff_factor: 退避因子（等待时间 = factor * (2 ^ 尝试次数)）
    """
    if retry_codes is None:
        retry_codes = [503, 504, 522, 524, 408, 429]

    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    # 检查HTTP状态码（如果返回response对象）
                    if hasattr(result, "status_code"):
                        status = result.status_code
                        if status in retry_codes and attempt < max_retries:
                            wait_time = backoff_factor * (2**attempt) + random.uniform(0, 1)
                            logger.warning(
                                f"HTTP {status}，{wait_time:.1f}s后重试（第{attempt+1}次）"
                            )
                            time.sleep(wait_time)
                            continue
                    return result
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait_time = backoff_factor * (2**attempt) + random.uniform(0, 1)
                        logger.warning(f"请求失败: {e}，{wait_time:.1f}s后重试（第{attempt+1}次）")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"重试{max_retries}次后仍失败")
                        raise

            raise last_exception

        return wrapper

    return decorator


# ========== 异常检测 ==========


class BlockDetector:
    """反爬虫拦截检测"""

    @staticmethod
    @staticmethod
    def is_blocked(response_text: str, status_code: int = 200) -> bool:
        """
        检测是否被反爬虫拦截（v2 - 精确检测）

        改进：
        1. 使用正则边界匹配，避免变量名误报（isRobot）
        2. 增加白名单模式，排除合法内容
        3. 优先检查特定拦截页面特征
        """
        import re

        text_lower = response_text.lower()

        # 状态码快速判断
        if status_code in [403, 429, 503]:
            return True

        # 白名单过滤（先排除误报）
        WHITELIST = [
            r'"isRobot"\s*:\s*false',  # Amazon 正常变量
            r'"isRobot"\s*:\s*true',
            r"isRobot\s*=\s*false",
            r"isRobot\s*=\s*true",
            r"//\s*robot",  # 注释
        ]
        for pattern in WHITELIST:
            if re.search(pattern, response_text, re.IGNORECASE):
                logger.debug(f"BlockDetector 白名单: {pattern}")
                return False

        # 关键拦截页面特征（最高置信度）
        if "challenges.cloudflare.com" in response_text and "jschl_vc" in response_text:
            return True
        if "aws.waf" in response_text and "access denied" in text_lower:
            return True
        if "captcha" in text_lower and "g-recaptcha" in response_text:
            return True

        # 完整短语匹配（避免单字误报）
        BLOCK_PATTERNS = [
            ("验证码", "验证码拦截"),
            ("verification", "验证码"),
            ("access denied", "访问拒绝"),
            ("unusual traffic", "异常流量"),
            ("too many requests", "请求过多"),
            ("请证明你不是机器人", "人机验证"),
            ("security check", "安全检查"),
            ("AWS WAF", "AWS WAF"),
            ("PerimeterX", "PerimeterX"),
            ("automated access", "自动访问拦截"),
        ]

        for pattern, desc in BLOCK_PATTERNS:
            if pattern in text_lower:
                logger.warning(f"拦截检测: {desc} ({pattern})")
                return True

        # robot 单字严格检测（排除变量名）
        if re.search(r"\brobot\b", text_lower):
            # 检查是否在合法上下文（如 isRobot 变量）
            if not re.search(r"isRobot\s*[=:]", response_text):
                logger.warning("拦截检测: robot 关键词（独立单词）")
                return True

        return False
