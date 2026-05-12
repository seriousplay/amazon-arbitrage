#!/usr/bin/env python3
"""
浏览器渲染器（基于 Playwright + 多层 Stealth）
用于绕过 Amazon、Cloudflare 等现代反爬虫检测
支持同步/异步双模式

2026 年最佳实践：
- 官方 Stealth 补丁（playwright-stealth v2）
- 7个关键手动补丁（navigator.webdriver, plugins, chrome.loadTimes/csi, permissions, WebGL, languages）
- 额外指纹混淆（Canvas, AudioContext, permissions 状态）
- 人类化行为（随机鼠标、渐进滚动、随机延迟）
"""

import asyncio
import logging
import random
from typing import Optional
from dataclasses import dataclass
from playwright.async_api import async_playwright, BrowserContext, Page

# Stealth 插件
try:
    from playwright_stealth import Stealth

    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

logger = logging.getLogger(__name__)

# ========== 配置结构 ==========


@dataclass
class RenderConfig:
    """渲染器配置"""

    headless: bool = True
    browser_type: str = "chromium"
    timeout: int = 30
    wait_until: str = "domcontentloaded"
    user_agent: Optional[str] = None
    stealth_enabled: bool = True
    stealth_patch_all: bool = True
    human_like: bool = True


# ========== 7个关键手动补丁（2026最新） ==========

STEALTH_PATCHES = """
// 7个关键补丁 - 2026年最新验证
(async () => {
  const patches = [];
  
  // Patch 1: navigator.webdriver → undefined（不是 false！）
  if (navigator.webdriver !== undefined) {
    Object.defineProperty(navigator, 'webdriver', {
      get: () => undefined,
      configurable: true
    });
    patches.push('navigator.webdriver');
  }
  
  // Patch 2: plugins 和 mimeTypes（伪造 Chrome 插件）
  const pluginData = [
    {name: 'PDF Viewer', description: 'Portable Document Format', filename: 'internal-pdf-viewer'},
    {name: 'Chrome PDF Viewer', description: '', filename: 'internal-pdf-viewer'},
    {name: 'Chromium PDF Viewer', description: '', filename: 'internal-pdf-viewer'},
    {name: 'Microsoft Edge PDF Viewer', description: '', filename: 'internal-pdf-viewer'},
    {name: 'WebKit built-in PDF', description: '', filename: 'internal-pdf-viewer'}
  ];
  if (navigator.plugins.length === 0) {
    Object.defineProperty(navigator, 'plugins', {
      get: () => Object.assign(pluginData, {
        item: i => pluginData[i],
        namedItem: n => pluginData.find(p => p.name === n),
        refresh: () => {},
        length: pluginData.length
      }),
      configurable: true
    });
    patches.push('navigator.plugins');
  }
  if (navigator.mimeTypes.length === 0) {
    Object.defineProperty(navigator, 'mimeTypes', {
      get: () => ({ length: 2, item: i => null, namedItem: n => null }),
      configurable: true
    });
    patches.push('navigator.mimeTypes');
  }
  
  // Patch 3: window.chrome（最关键 - 大部分库缺失 loadTimes/csi）
  if (!window.chrome) window.chrome = {};
  const chrome = window.chrome;
  if (!chrome.loadTimes) {
    chrome.loadTimes = function() {
      return {
        requestTime: Date.now() / 1000,
        startLoadTime: Date.now() / 1000,
        commitLoadTime: Date.now() / 1000,
        finishDocumentLoadTime: 0,
        finishLoadTime: 0,
        firstPaintTime: 0,
        firstPaintAfterLoadTime: 0,
        navigationType: 'Other',
        wasFetchedViaSpdy: false,
        wasNpnNegotiated: false,
        npnNegotiatedProtocol: 'unknown',
        wasAlternateProtocolAvailable: false,
        connectionInfo: 'h2'
      };
    };
    patches.push('chrome.loadTimes');
  }
  if (!chrome.csi) {
    chrome.csi = function() {
      return {
        startE: Date.now(),
        onloadT: Date.now(),
        pageT: 3000 + Math.random() * 1000,
        tran: 15
      };
    };
    patches.push('chrome.csi');
  }
  if (!chrome.app) {
    chrome.app = {
      isInstalled: false,
      InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
      RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
    };
    patches.push('chrome.app');
  }
  if (!chrome.runtime) {
    chrome.runtime = {
      OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
      OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
      PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
      PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
      RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' },
      id: undefined,
      connect: () => {},
      sendMessage: () => {}
    };
    patches.push('chrome.runtime');
  }
  
  // Patch 4: navigator.permissions（通知权限）
  if (navigator.permissions && navigator.permissions.query) {
    const originalQuery = navigator.permissions.query;
    navigator.permissions.query = (params) => {
      if (params.name === 'notifications') {
        return Promise.resolve({ state: Notification.permission, onchange: null });
      }
      return originalQuery(params);
    };
    patches.push('navigator.permissions');
  }
  
  // Patch 5: WebGL Vendor/Renderer
  const getParameter = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    if (parameter === 7936) return 'WebKit';  // UNMASKED_VENDOR_WEBGL
    if (parameter === 7937) return 'WebKit WebGL Engine';  // UNMASKED_RENDERER_WEBGL
    return getParameter.call(this, parameter);
  };
  patches.push('WebGL');
  
  // Patch 6: languages 和 locale
  if (navigator.languages && navigator.languages.length > 0) {
    Object.defineProperty(navigator, 'languages', {
      get: () => ['en-US', 'en'],
      configurable: true
    });
    patches.push('navigator.languages');
  }
  if (navigator.language !== 'en-US') {
    Object.defineProperty(navigator, 'language', {
      get: () => 'en-US',
      configurable: true
    });
    patches.push('navigator.language');
  }
  
  // Patch 7: hardwareConcurrency 和 deviceMemory
  if (navigator.hardwareConcurrency !== 8) {
    Object.defineProperty(navigator, 'hardwareConcurrency', {
      get: () => 8,
      configurable: true
    });
    patches.push('navigator.hardwareConcurrency');
  }
  if (navigator.deviceMemory !== 8) {
    Object.defineProperty(navigator, 'deviceMemory', {
      get: () => 8,
      configurable: true
    });
    patches.push('navigator.deviceMemory');
  }
  
  // Patch 8: 修正 platform
  if (navigator.platform === 'MacIntel' || navigator.platform === 'Win32') {
    Object.defineProperty(navigator, 'platform', {
      get: () => 'MacIntel',
      configurable: true
    });
    patches.push('navigator.platform');
  }
  
  console.log('[Stealth] 关键补丁已应用:', patches.join(', '));
})();
"""

# ========== 异步浏览器渲染器 ==========


class BrowserRenderer:
    """异步浏览器渲染器（集成三层 Stealth）"""

    def __init__(self, config: RenderConfig = None):
        self.config = config or RenderConfig()
        self._playwright: Optional[async_playwright] = None
        self._browser: Optional[BrowserContext] = None
        self._context: Optional[BrowserContext] = None
        self._initialized = False

    def _get_random_ua(self) -> str:
        """随机 User-Agent（真实浏览器池）"""
        uas = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
        ]
        return random.choice(uas)

    async def init(self) -> None:
        """初始化浏览器实例（独立控制模式）"""
        if self._initialized:
            return

        logger.info("启动 Playwright（Stealth 模式）...")

        try:
            # 启动 Playwright
            self._playwright = await async_playwright().start()

            # 启动参数（反检测）
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-web-security",
                "--disable-features=AudioServiceOutOfProcess",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--no-first-run",
                "--no-zygote",
                "--disable-gpu",
            ]

            self._browser = await self._playwright.chromium.launch(
                headless=self.config.headless, args=launch_args
            )

            # 创建上下文（模拟真实浏览器）
            context_options = {
                "user_agent": self.config.user_agent or self._get_random_ua(),
                "viewport": {"width": 1920, "height": 1080},
                "locale": "en-US",
                "timezone_id": "America/New_York",
                "color_scheme": "light",
                "reduced_motion": "no-preference",
                "forced_colors": "none",
            }

            self._context = await self._browser.new_context(**context_options)

            # === 步骤1: 应用官方 Stealth 补丁 ===
            if STEALTH_AVAILABLE and self.config.stealth_enabled:
                try:
                    stealth = Stealth()
                    await stealth.apply_stealth_async(self._context)
                    logger.info("✓ 官方 Stealth 补丁已应用")
                except Exception as e:
                    logger.warning(f"官方 Stealth 失败: {e}")

            # === 步骤2: 注入 7 个关键手动补丁 ===
            if self.config.stealth_patch_all:
                try:
                    await self._context.add_init_script(STEALTH_PATCHES)
                    logger.info(
                        "✓ 7个关键手动补丁已注入（navigator.webdriver, plugins, chrome.loadTimes/csi, permissions, WebGL, languages）"
                    )
                except Exception as e:
                    logger.warning(f"手动补丁注入失败: {e}")

            # === 步骤3: 额外指纹混淆 ===
            await self._apply_extra_fingerprint_masking()

            self._initialized = True
            logger.info("✓ Stealth 浏览器初始化完成（三层防御）")

        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            raise

    async def _apply_extra_fingerprint_masking(self) -> None:
        """额外指纹混淆（Canvas、AudioContext、permissions）"""
        extra_script = """
        // 额外混淆：修复剩余的检测向量
        
        // 1. 确保 chrome 对象完整
        if (!window.chrome) window.chrome = {};
        if (!window.chrome.runtime) window.chrome.runtime = {};
        
        // 2. 修正 permissions.query 返回值（denied → prompt）
        const originalQuery = window.navigator.permissions?.query;
        if (originalQuery) {
            window.navigator.permissions.query = function(parameters) {
                return originalQuery.call(this, parameters).then(result => {
                    if (result.state === 'denied' && parameters.name === 'notifications') {
                        return Promise.resolve({ state: 'prompt', onchange: null });
                    }
                    return result;
                });
            };
        }
        
        // 3. WebGL 参数（真实 GPU）
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            const original = getParameter.call(this, parameter);
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
            if (parameter === 7936) return 'Intel Inc.';
            if (parameter === 7937) return 'Intel Iris OpenGL Engine';
            return original;
        };
        
        // 4. Canvas 指纹（添加微小噪声）
        const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
        CanvasRenderingContext2D.prototype.getImageData = function(...args) {
            const imageData = originalGetImageData.apply(this, args);
            const data = imageData.data;
            for (let i = 0; i < data.length; i += 4) {
                data[i] = Math.min(255, data[i] + Math.floor(Math.random() * 2));
                data[i+1] = Math.min(255, data[i+1] + Math.floor(Math.random() * 2));
                data[i+2] = Math.min(255, data[i+2] + Math.floor(Math.random() * 2));
            }
            return imageData;
        };
        
        // 5. AudioContext 指纹
        if (window.AudioContext || window.webkitAudioContext) {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            const originalCreateChannelData = AudioContextClass.prototype.createChannelData;
            if (originalCreateChannelData) {
                AudioContextClass.prototype.createChannelData = function(length) {
                    const data = originalCreateChannelData.call(this, length);
                    for (let i = 0; i < data.length; i++) {
                        data[i] += (Math.random() - 0.5) * 0.01;
                    }
                    return data;
                };
            }
        }
        
        console.log('[Stealth] 额外指纹混淆已应用');
        """
        try:
            await self._context.add_init_script(extra_script)
            logger.debug("额外指纹混淆已应用")
        except Exception as e:
            logger.warning(f"额外混淆失败: {e}")

    async def render(self, url: str, wait_for: str = None, scroll_to_bottom: bool = False) -> str:
        """渲染页面并返回 HTML"""
        if not self._initialized:
            await self.init()

        logger.info(f"导航: {url}")
        page = await self._context.new_page()

        try:
            # 人类化行为：随机鼠标移动
            if self.config.human_like:
                await self._human_move(page)

            # 导航
            response = await page.goto(
                url, wait_until=self.config.wait_until, timeout=self.config.timeout * 1000
            )

            if not response or response.status >= 400:
                raise Exception(f"HTTP {response.status if response else 'no response'}")

            # 等待关键元素
            if wait_for:
                try:
                    await page.wait_for_selector(wait_for, timeout=10000)
                except:
                    logger.warning(f"等待选择器超时: {wait_for}")

            # 人类化滚动
            if scroll_to_bottom:
                await self._human_scroll(page)
            else:
                if self.config.human_like:
                    await asyncio.sleep(random.uniform(1, 3))

            # 获取 HTML
            html = await page.content()
            logger.info(f"✓ 渲染完成: {len(html):,} 字节")
            return html

        finally:
            await page.close()

    async def _human_move(self, page: Page) -> None:
        """模拟人类鼠标移动"""
        x = random.randint(100, 500)
        y = random.randint(100, 500)
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.5, 1.5))

    async def _human_scroll(self, page: Page) -> None:
        """模拟人类滚动（渐进式）"""
        logger.debug("人类化滚动...")
        scroll_height = await page.evaluate("document.body.scrollHeight")
        viewport = await page.evaluate("window.innerHeight")

        positions = []
        current = 0
        while current < scroll_height - viewport:
            step = random.randint(200, 600)
            current += step
            positions.append(min(current, scroll_height - viewport))

        for pos in positions:
            await page.evaluate(f"window.scrollTo(0, {pos})")
            await asyncio.sleep(random.uniform(0.3, 1.0))

        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(random.uniform(0.5, 1.5))

    async def close(self):
        """清理资源"""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._initialized = False
        logger.info("浏览器已关闭")


# ========== 同步渲染器 ==========


class SyncRenderer:
    """同步渲染器（内部管理 asyncio）"""

    def __init__(self, config: RenderConfig = None):
        self.config = config or RenderConfig()
        self._loop = None

    def render(self, url: str, wait_for: str = None, scroll_to_bottom: bool = False) -> str:
        """同步渲染（阻塞式）"""
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

        renderer = BrowserRenderer(self.config)

        async def _render():
            await renderer.init()
            try:
                return await renderer.render(url, wait_for, scroll_to_bottom)
            finally:
                await renderer.close()

        return self._loop.run_until_complete(_render())

    def close(self):
        """清理（占位）"""
        pass


# ========== 便捷函数 ==========


async def render_page_async(
    url: str, config: RenderConfig = None, wait_for: str = None, scroll: bool = False
) -> str:
    """异步便捷函数"""
    renderer = BrowserRenderer(config)
    await renderer.init()
    try:
        return await renderer.render(url, wait_for, scroll)
    finally:
        await renderer.close()


def render_page_sync(
    url: str, config: RenderConfig = None, wait_for: str = None, scroll: bool = False
) -> str:
    """同步便捷函数"""
    renderer = SyncRenderer(config)
    try:
        return renderer.render(url, wait_for, scroll)
    finally:
        renderer.close()
