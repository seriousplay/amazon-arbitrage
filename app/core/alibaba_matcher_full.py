from app.utils.anti_block import UserAgentRotator, DelayManager, ProxyPool, BlockDetector
import requests
import os
import json
from bs4 import BeautifulSoup
import time
import logging
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from urllib.parse import quote_plus
import random
import numpy as np
import cv2

# 技能根目录（绝对路径）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 反爬虫工具

logger = logging.getLogger(__name__)


@dataclass
class AlibabaProduct:
    """1688 商品信息"""
    pid: str  # 商品ID
    title: str
    price: float  # 单价（元）
    min_order_qty: int  # 起订量
    supplier: str
    supplier_url: str
    product_url: str
    location: str  # 产地/发货地
    similarity_score: Optional[float] = None  # 与Amazon标题的相似度


# 中文停用词（用于关键词提取）
STOPWORDS = {
    '的', '了', '和', '是', '在', '我们', '你', '我', '他', '她', '它',
    '这', '那', '里', '来', '去', '到', '有', '没', '不', '也', '都',
    '就', '才', '还', '又', '要', '会', '能', '让', '使', '把', '被',
    'for', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'of',
    'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'with', 'by', 'from', 'up', 'down', 'out', 'off', 'over', 'under',
}


class AlibabaMatcher:
    """1688 商品匹配器（增强反爬虫）"""

    BASE_URL = "https://s.1688.com"
    SEARCH_PATH = "/selloffer/offer_search.htm"

    def __init__(self,
                 request_delay: tuple = (2, 5),
                 proxy: Optional[Dict] = None,
                 ua_rotator: Optional[UserAgentRotator] = None,
                 delay_manager: Optional[DelayManager] = None,
                 proxy_pool: Optional[ProxyPool] = None,
                 use_renderer: bool = False,
        auto_mode: bool = False,  # 非交互模式，跳过手动扫码
                 renderer_config: Optional[Dict] = None):
        self.session = requests.Session()

        # 反爬虫组件
        self.ua_rotator = ua_rotator or UserAgentRotator()
        self.delay_manager = delay_manager or DelayManager(
            min_delay=request_delay[0],
            max_delay=request_delay[1]
        )
        self.proxy_pool = proxy_pool
        self.single_proxy = proxy

        self.request_count = 0
        self.block_count = 0
        self.logger = logging.getLogger(__name__)

        # 渲染器模式
        self.use_renderer = use_renderer
        self.auto_mode = auto_mode
        self.renderer = None
        if use_renderer:
            from app.utils.renderer import SyncRenderer, RenderConfig
            renderer_config = renderer_config or {}
            config = RenderConfig(
                headless=renderer_config.get('headless', True),  # 默认后台
                stealth_enabled=renderer_config.get('stealth_enabled', True),
                user_agent=renderer_config.get('user_agent')
            )
            self.renderer = SyncRenderer(config=config)
            # 直接管理 Playwright 实例（用于 1688 登录）
            self._playwright = None
            self._browser = None
            self._context = None

            self.logger.info("✓ 1688 匹配器启用 Playwright 渲染器（Stealth 模式）")

            # 尝试加载已保存的 cookies
            self.cookies_file = os.path.join(PROJECT_ROOT, "data", "cookies", "1688_cookies.json")
            self.use_renderer = use_renderer
            self.auto_mode = auto_mode
            self._load_cookies()

    def cleanup(self):
        """关闭 Playwright 资源"""
        try:
            if self._context:
                self._context.close()
                self._context = None
            if self._browser:
                self._browser.close()
                self._browser = None
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
            self.logger.info("✓ Playwright 资源已释放")
        except Exception as e:
            self.logger.debug(f"清理异常: {e}")

    def _get_random_ua(self) -> str:
        """随机 User-Agent（备用）"""
        import random
        uas = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        ]
        return random.choice(uas)

    def _random_delay(self):
        import random
        time.sleep(random.uniform(self.delay_range[0], self.delay_range[1]))

    def _extract_price(self, price_text: str) -> Optional[float]:
        """提取价格（处理区间价格，取最低价）"""
        if not price_text:
            return None
        # 匹配 "¥12.5" 或 "12.5-25.0" 取最小
        numbers = re.findall(r'(\d+(?:\.\d+)?)', price_text)
        if numbers:
            return float(min(numbers))
        return None

    def _extract_int(self, text: str) -> Optional[int]:
        """提取整数"""
        match = re.search(r'(\d+)', text.replace(',', ''))
        return int(match.group(1)) if match else None

    def _extract_search_keyword(self, title: str) -> str:
        """从 Amazon 标题提取 1688 搜索关键词"""
        if not title:
            return ""

        # 移除品牌、型号、包装规格等噪声
        noise_patterns = [
            r'\d+\s*pack',      # "12 pack"
            r'\d+\s*count',     # "24 count"
            r'\d+\s*ct',        # "12 ct"
            r'for\s+\w+',       # "for dogs"
            r'with',            # "with leash"
            r'\([^)]*\)',           # 括号内容
            r'\[[^\]]*\]',          # 方括号内容
            r'(?:size|large|small|medium|x[ls]|xl|xxl)',  # 尺寸词
            r'(?:ounces?|lbs?|oz|g|kg)',  # 单位
            r'[^\w\s]',             # 标点
        ]

        keyword = title
        for pattern in noise_patterns:
            keyword = re.sub(pattern, ' ', keyword, flags=re.IGNORECASE)

        # 提取核心名词短语（保留最多 4 个词）
        words = [w for w in keyword.split() if len(
            w) > 2 and w not in STOPWORDS]
        keyword = ' '.join(words[:4])

        # 如果关键词为空，返回原标题前 20 字符
        return keyword or title[:20]

    def _load_cookies(self) -> bool:
        """加载已保存的 1688 cookies"""
        cookie_file = 'data/cookies/1688_cookies.json'

        if not os.path.exists(cookie_file):
            self.logger.info("未找到 cookies 文件，需要登录")
            return False

        try:
            import json
            with open(cookie_file, 'r') as f:
                cookies = json.load(f)

            if not self.renderer:
                return False

            # 先访问 1688 域名
            html = self.renderer.render("https://www.1688.com")
            self.renderer.page.context.add_cookies(cookies)

            self.logger.info("✓ 已加载 1688 cookies")

            # 验证是否有效
            self.renderer.page.reload()
            time.sleep(2)
            html = self.renderer.page.content()

            if not self._is_login_page(html):
                self.logger.info("✓ Cookies 有效，已登录")
                return True
            else:
                self.logger.info("Cookies 已过期，需要重新登录")
                return False

        except Exception as e:
            self.logger.warning(f"加载 cookies 失败: {e}")
            return False

    def _ensure_login_with_renderer(self) -> bool:
        """确保已登录 1688（三层策略：上下文复用 → cookies 恢复 → 扫码登录）
        返回 True 表示登录成功，False 表示失败
        """
        self.logger.info("检查登录状态...")
        
        try:
            from playwright.sync_api import sync_playwright
            import json
            
            # === 策略 1: 测试现有上下文 ===
            if self._context:
                try:
                    test_page = self._context.new_page()
                    test_page.goto("https://www.1688.com", wait_until='domcontentloaded', timeout=10000)
                    time.sleep(1)
                    html = test_page.content()
                    test_page.close()
                    if not self._is_login_page(html):
                        self.logger.info("✓ 使用现有登录上下文")
                        return True
                    else:
                        self.logger.info("现有上下文已过期，尝试恢复 cookies")
                        self._context.close()
                        self._context = None
                except Exception as e:
                    self.logger.debug(f"测试上下文失败: {e}")
                    self._context = None
            
            # === 策略 2: 加载保存的 cookies ===
            if os.path.exists(self.cookies_file):
                self.logger.info("发现 cookies，尝试自动恢复...")
                try:
                    if not self._playwright:
                        self._playwright = sync_playwright().start()
                        self._browser = self._playwright.chromium.launch(headless=False)
                    self._context = self._browser.new_context()
                    
                    # 先访问域名
                    temp_page = self._context.new_page()
                    temp_page.goto("https://www.1688.com", wait_until='domcontentloaded', timeout=10000)
                    time.sleep(1)
                    temp_page.close()
                    
                    # 加载 cookies
                    with open(self.cookies_file, 'r', encoding='utf-8') as f:
                        cookies = json.load(f)
                    # 过滤 domain
                    # 1688 登录需要跨域 cookie（taobao.com），全部加载
                    valid_cookies = [c for c in cookies if any(
                        d in c.get('domain', '') for d in ['1688.com', 'taobao.com', 'tmall.com']
                    )]
                    self._context.add_cookies(valid_cookies)
                    
                    # 验证
                    verify_page = self._context.new_page()
                    verify_page.goto("https://www.1688.com", wait_until='domcontentloaded', timeout=10000)
                    time.sleep(1)
                    html = verify_page.content()
                    verify_page.close()
                    
                    if not self._is_login_page(html):
                        self.logger.info("✓ Cookies 自动恢复成功")
                        return True
                    else:
                        self.logger.info("Cookies 已过期，需要重新登录")
                        self._context.close()
                        self._context = None
                except Exception as e:
                    self.logger.warning(f"Cookies 恢复失败: {e}")
                    if self._context:
                        try: self._context.close()
                        except: pass
                    self._context = None
            
            # === 策略 3: 打开浏览器扫码 ===
            self.logger.warning("需要手动扫码登录")
            if self.auto_mode:
                self.logger.info("auto_mode 开启，跳过扫码（登录失败）")
                return False
            
            if not self._playwright:
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(headless=False)
            self._context = self._browser.new_context()
            
            page = self._context.new_page()
            page.goto("https://www.1688.com", wait_until='domcontentloaded', timeout=15000)
            time.sleep(2)
            
            # 检查是否已登录（有时直接打开就是登录状态）
            html = page.content()
            if not self._is_login_page(html):
                self.logger.info("✓ 已登录（无需扫码）")
                page.close()
                # 保存 cookies
                cookies = self._context.cookies()
                filtered = [c for c in cookies if any(d in c.get('domain', '') for d in ['1688.com', 'taobao.com', 'tmall.com'])]
                with open(self.cookies_file, 'w', encoding='utf-8') as f:
                    json.dump(filtered, f, ensure_ascii=False, indent=2)
                return True
            
            # 提示扫码
            self.logger.info("=" * 60)
            self.logger.info("请在打开的浏览器中扫码登录 1688")
            self.logger.info("登录完成后，按回车键继续...")
            self.logger.info("=" * 60)
            input()
            
            # 验证
            html = page.content()
            if self._is_login_page(html):
                self.logger.error("仍然未登录")
                page.close()
                return False
            
            self.logger.info("✓ 登录成功")
            cookies = self._context.cookies()
            filtered = [c for c in cookies if any(d in c.get('domain', '') for d in ['1688.com', 'taobao.com', 'tmall.com'])]
            with open(self.cookies_file, 'w', encoding='utf-8') as f:
                json.dump(filtered, f, ensure_ascii=False, indent=2)
            self.logger.info(f"✓ Cookies 已保存 ({len(filtered)} 条)")
            
            page.close()
        except Exception as e:
            self.logger.error(f"登录过程异常: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _is_login_page(self, html: str) -> bool:
        """判断当前页面是否为登录页"""
        html_lower = html.lower()

        login_indicators = [
            '手机号', '验证码', '短信验证', '动态密码', '二维码',
            'login', '登录', 'sign in', '用户名', '密码', '密码框',
            '扫码登录', '免费注册', '忘记密码'
        ]
        for kw in login_indicators:
            if kw in html_lower:
                return True
        
        # 方法 2: 检查表单结构（密码输入框）
        if 'type="password"' in html or "type='password'" in html:
            return True
        
        # 方法 3: 检查特定元素
        login_selectors = [
            'input[name="loginId"]',
            'input[name="password"]',
            '.login-box',
            '#login-form',
            '.nc_iconfont'
        ]
        for sel in login_selectors:
            if sel in html:
                return True
        
        return False

    def _check_and_bypass_slider(self, page_obj=None, max_attempts: int = 3) -> bool:
        """四层防御滑块破解：智能元素定位 → 纯视觉检测 → 智能拖动 → 验证重试
        返回 True 表示破解成功（或无需破解），False 表示彻底失败
        """
        import sys, time, os, json
        import cv2, numpy as np
        
        sys.stderr.write("[DEBUG] _check_and_bypass_slider: 开始检测滑块\n")
        
        if page_obj is None:
            if not self._context:
                self.logger.error("无可用浏览器上下文")
                return False
            page = self._context.new_page()
            need_close = True
        else:
            page = page_obj
            need_close = False
        
        try:
            page.goto("https://www.1688.com", wait_until='domcontentloaded', timeout=15000)
            time.sleep(2)
            
            # ========== Layer 1: 智能元素定位（最快） ==========
            slider_selectors = [
                ".nc_iconfont.btn_slide",
                ".nc-lang-cnt .btn_slide",
                "span[class*='nc_iconfont']",
                "div[class*='nc-container'] span[class*='slide']",
                ".baxia-dialog-content .nc_iconfont"
            ]
            
            slider_el = None
            for sel in slider_selectors:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0 and el.is_visible():
                        slider_el = el
                        sys.stderr.write(f"[DEBUG] 找到滑块元素: {sel}\n")
                        break
                except:
                    pass
            
            if slider_el:
                # 获取滑块位置
                slider_box = slider_el.bounding_box()
                if not slider_box:
                    # 尝试通过 JS 获取
                    slider_box = page.evaluate("""() => {
                        const el = document.querySelector('.nc_iconfont.btn_slide, .nc-lang-cnt .btn_slide');
                        if (el) {
                            const rect = el.getBoundingClientRect();
                            return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
                        }
                        return null;
                    }""")
                
                if slider_box and slider_box.get('width', 0) > 0:
                    # 计算拖动距离（滑块宽度 ≈ 40px，向右拖动到容器右侧）
                    start_x = slider_box['x'] + slider_box['width'] // 2
                    
                    # 尝试找到目标容器
                    container = page.locator('.nc-container').first
                    container_box = None
                    if container.count() > 0:
                        try:
                            container_box = container.bounding_box()
                        except:
                            pass
                    
                    if not container_box:
                        container_box = page.evaluate("""() => {
                            const el = document.querySelector('.nc-container, .baxia-dialog-content');
                            if (el) {
                                const rect = el.getBoundingClientRect();
                                return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
                            }
                            return null;
                        }""")
                    
                    if container_box:
                        # 目标位置：容器右边界 - 滑块半宽 - 右边距
                        target_x = container_box['x'] + container_box['width'] - slider_box['width'] // 2 - 5
                        distance = target_x - start_x
                    else:
                        # 保守估计：拖动 200-300px
                        distance = 250
                    
                    sys.stderr.write(f"[DEBUG] 滑块位置: x={start_x}, 拖动距离: {distance}px\n")
                    
                    # 执行拖动
                    page.mouse.move(start_x, slider_box['y'] + slider_box['height'] // 2)
                    page.mouse.down()
                    
                    points = self._generate_realistic_trajectory(distance, start_x, slider_box['y'] + slider_box['height'] // 2)
                    for px, py, dt in points:
                        page.mouse.move(px, py)
                        time.sleep(dt)
                    
                    page.mouse.up()
                    time.sleep(2)
                    
                    # 验证
                    try:
                        if page.locator(".nc_iconfont.btn_slide").count() == 0:
                            sys.stderr.write("[DEBUG] Layer 1 成功：滑块消失\n")
                            return True
                    except:
                        pass
            
            # ========== Layer 2: 纯视觉检测（不依赖 DOM） ==========
            sys.stderr.write("[DEBUG] Layer 1 失败，尝试 Layer 2 (纯视觉)\n")
            
            # 截图
            screenshot_path = os.path.join(self.temp_dir, 'slider_full.png')
            page.screenshot(path=screenshot_path, full_page=True)
            full_img = cv2.imread(screenshot_path)
            
            if full_img is not None:
                # 定位滑块
                slider_info = self._find_slider_by_vision(full_img)
                if slider_info:
                    x, y, w, h = slider_info[:4]
                    sys.stderr.write(f"[DEBUG] 视觉定位滑块: x={x}, y={y}, w={w}, h={h}\n")
                    
                    # 提取滑块图像
                    slider_img = full_img[y:y+h, x:x+w]
                    
                    # 定位缺口
                    gap_info = self._find_gap_advanced(full_img, slider_img)
                    if gap_info:
                        gx, gy, gw, gh = gap_info
                        sys.stderr.write(f"[DEBUG] 视觉定位缺口: x={gx}, y={gy}, w={gw}, h={gh}\n")
                        
                        # 计算拖动距离（缺口右边缘 - 滑块中心）
                        slider_cx = x + w // 2
                        gap_cx = gx + gw // 2
                        distance = gap_cx - slider_cx
                        
                        if distance <= 10:
                            distance = 20  # 最小拖动
                        
                        sys.stderr.write(f"[DEBUG] 计算拖动距离: {distance}px\n")
                        
                        # 执行拖动
                        page.mouse.move(slider_cx, y + h // 2)
                        page.mouse.down()
                        
                        points = self._generate_realistic_trajectory(distance, slider_cx, y + h // 2)
                        for px, py, dt in points:
                            page.mouse.move(px, py)
                            time.sleep(dt)
                        
                        page.mouse.up()
                        time.sleep(2)
                        
                        # 验证
                        try:
                            if page.locator(".nc_iconfont.btn_slide").count() == 0:
                                sys.stderr.write("[DEBUG] Layer 2 成功：滑块消失\n")
                                return True
                        except:
                            pass
            
            # ========== Layer 3: 随机拖动降级 ==========
            sys.stderr.write("[DEBUG] Layer 2 失败，尝试 Layer 3 (随机拖动)\n")
            try:
                slider_el = page.locator('.nc_iconfont.btn_slide').first
                if slider_el.count() > 0:
                    box = slider_el.bounding_box()
                    if box:
                        cx = box['x'] + box['width'] // 2
                        cy = box['y'] + box['height'] // 2
                        distance = 250
                        
                        page.mouse.move(cx, cy)
                        page.mouse.down()
                        
                        points = self._generate_realistic_trajectory(distance, cx, cy)
                        for px, py, dt in points:
                            page.mouse.move(px, py)
                            time.sleep(dt)
                        
                        page.mouse.up()
                        time.sleep(2)
                        
                        if page.locator(".nc_iconfont.btn_slide").count() == 0:
                            sys.stderr.write("[DEBUG] Layer 3 成功\n")
                            return True
            except Exception as e:
                sys.stderr.write(f"[DEBUG] Layer 3 失败: {e}\n")
            
            sys.stderr.write("[DEBUG] 滑块验证失败或未检测到\n")
            return False
            
        except Exception as e:
            sys.stderr.write(f"[DEBUG] 滑块破解异常: {e}\n")
            import traceback
            traceback.print_exc()
            return False
        finally:
            if need_close:
                try:
                    page.close()
                except:
                    pass


    def _find_slider_by_vision(self, full_img: np.ndarray) -> Optional[Tuple[int, int, int, int, np.ndarray]]:
        """纯视觉检测：在全图中定位滑块位置"""
        import sys
        try:
            h, w = full_img.shape[:2]
            hsv = cv2.cvtColor(full_img, cv2.COLOR_BGR2HSV)
            lower_blue = np.array([100, 120, 100])
            upper_blue = np.array([130, 255, 255])
            blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            blue_mask = cv2.morphologyEx(blue_mask, cv2.MORPH_CLOSE, kernel)
            blue_mask = cv2.morphologyEx(blue_mask, cv2.MORPH_OPEN, kernel)
            contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            candidates = []
            for cnt in contours:
                x, y, cw, ch = cv2.boundingRect(cnt)
                area = cv2.contourArea(cnt)
                aspect = cw / ch if ch > 0 else 0
                if 1.5 <= aspect <= 5.0 and 200 <= area <= 15000:
                    roi = full_img[y:y+ch, x:x+cw]
                    if roi.size > 0:
                        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                        blue_pixels = cv2.inRange(hsv_roi, lower_blue, upper_blue).sum()
                        blue_ratio = blue_pixels / (cw * ch * 3) if cw * ch > 0 else 0
                        if blue_ratio > 0.1:
                            candidates.append((x, y, cw, ch, area, blue_ratio))
            if candidates:
                candidates.sort(key=lambda c: c[4] * c[5], reverse=True)
                x, y, w, h, area, ratio = candidates[0]
                sys.stderr.write(f"[DEBUG] 视觉定位滑块: x={x}, y={y}, w={w}, h={h}\n")
                return (x, y, w, h, full_img[y:y+h, x:x+w])
            return None
        except Exception as e:
            sys.stderr.write(f"[DEBUG] _find_slider_by_vision 异常: {e}\n")
            return None

    def _find_gap_advanced(self, bg_img: np.ndarray, slider_img: np.ndarray,
                           full_img: np.ndarray, slider_box: dict) -> Optional[int]:
        """高级缺口识别：多算法融合"""
        try:
            bg_gray = cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY) if len(bg_img.shape) == 3 else bg_img
            slider_gray = cv2.cvtColor(slider_img, cv2.COLOR_BGR2GRAY) if len(slider_img.shape) == 3 else slider_img
            bg_edges = cv2.Canny(bg_gray, 50, 150)
            slider_edges = cv2.Canny(slider_gray, 50, 150)
            result = cv2.matchTemplate(bg_edges, slider_edges, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            sys.stderr.write(f"[DEBUG] 模板匹配: 置信度={max_val:.3f}, 位置={max_loc}\n")
            if max_val > 0.3:
                gap_x = max_loc[0] + slider_img.shape[1] // 3
                return gap_x
            # 差分法
            diff = cv2.absdiff(bg_gray, slider_gray)
            _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(largest)
                if w < h * 2 and w > 5:
                    sys.stderr.write(f"[DEBUG] 差分法识别缺口: x={x}\n")
                    return x
            return None
        except Exception as e:
            sys.stderr.write(f"[DEBUG] _find_gap_advanced 异常: {e}\n")
            return None

    def _generate_realistic_trajectory(self, distance: int, start_x: int, start_y: int) -> List[Tuple[int, int]]:
        """生成拟人的拖动轨迹"""
        points = []
        num_points = max(15, min(40, distance // 3))
        end_x = start_x + distance
        end_y = start_y
        cp1_x = start_x + distance * random.uniform(0.15, 0.25)
        cp1_y = start_y + random.uniform(-2, 2)
        cp2_x = start_x + distance * random.uniform(0.70, 0.80)
        cp2_y = start_y + random.uniform(-2, 2)
        for t in np.linspace(0, 1, num_points):
            x = (1-t)**3 * start_x + 3*(1-t)**2 * t * cp1_x + 3*(1-t) * t**2 * cp2_x + t**3 * end_x
            y = (1-t)**3 * start_y + 3*(1-t)**2 * t * cp1_y + 3*(1-t) * t**2 * cp2_y + t**3 * end_y
            jitter_x = random.uniform(-0.3, 0.3)
            jitter_y = random.uniform(-0.3, 0.3)
            points.append((int(x + jitter_x), int(y + jitter_y)))
        return points


    def _search_with_renderer(self, keyword: str, page: int = 1) -> List[AlibabaProduct]:
        """使用 Playwright 渲染器搜索 1688（登录后直接渲染搜索页 + 滑块自动破解）"""
        import sys
        sys.stderr.write(f"[DEBUG] _search_with_renderer: keyword={keyword}, page={page}\n")

        products = []

        try:
            # 1. 确保已登录
            sys.stderr.write("[DEBUG] 调用 _ensure_login_with_renderer...\n")
            login_ok = self._ensure_login_with_renderer()
            sys.stderr.write(f"[DEBUG] 登录结果: {login_ok}, self._context={self._context}\n")

            if not login_ok or not self._context:
                self.logger.error("登录失败或上下文丢失")
                return []

            # 2. 使用已登录上下文渲染搜索页
            sys.stderr.write("[DEBUG] 上下文正常，开始渲染搜索页...\n")
            page_obj = self._context.new_page()
            try:
                encoded_keyword = quote_plus(keyword)
                search_url = f"https://s.1688.com/selloffer/offer_search.htm?keywords={encoded_keyword}&page={page}"

                self.logger.info(f"渲染搜索页: {search_url[:80]}")
                page_obj.goto(search_url, wait_until='domcontentloaded')
                time.sleep(random.uniform(2, 4))

                # ========== 新增：滑块验证码检测与自动破解 ==========
                sys.stderr.write("[DEBUG] 检查滑块验证码...\n")
                slider_passed = self._check_and_bypass_slider(page_obj)

                if not slider_passed:
                    sys.stderr.write("[DEBUG] 滑块验证失败或未检测到，尝试重新加载\n")
                    # 重新加载一次页面
                    page_obj.reload(wait_until='domcontentloaded')
                    time.sleep(2)
                    slider_passed = self._check_and_bypass_slider(page_obj)

                if not slider_passed:
                    self.logger.warning("滑块验证码未通过，放弃本次搜索")
                    return []

                # 等待页面稳定
                time.sleep(random.uniform(1, 2))
                # ========== 滑块破解结束 ==========

                html = page_obj.content()
                sys.stderr.write(f"[DEBUG] 搜索页 HTML 大小: {len(html):,} 字节\n")

                # 保存 HTML 用于调试
                debug_path = os.path.join(SKILL_ROOT, 'data', 'raw', f'debug_search_{keyword[:20]}_p{page}.html')
                os.makedirs(os.path.dirname(debug_path), exist_ok=True)
                with open(debug_path, 'w', encoding='utf-8') as f:
                    f.write(html)
                sys.stderr.write(f"[DEBUG] 已保存: {debug_path}\n")

                # 检查拦截
                if self._is_login_page(html):
                    sys.stderr.write("[DEBUG] 检测到登录页\n")
                    self.logger.error("搜索页被重定向到登录页")
                    return []

                if '验证码' in html or 'captcha' in html.lower():
                    sys.stderr.write("[DEBUG] 检测到验证码（破解后仍存在）\n")
                    self.logger.warning("搜索页仍有验证码，可能破解失败")
                    # 不立即返回，尝试解析

                # 解析商品
                products = self._parse_1688_list(html)
                self.logger.info(f"✓ 解析完成，找到 {len(products)} 个商品")

            finally:
                page_obj.close()

        except Exception as e:
            self.logger.error(f"渲染器搜索失败: {e}")
            import traceback
            traceback.print_exc()

        return products

    def search_products(self, keyword: str, page: int = 1) -> List[AlibabaProduct]:
        """
        在 1688 搜索商品（支持渲染器/requests 双模式）

        Args:
            keyword: 搜索关键词
            page: 页码

        Returns:
            商品列表
        """
        products = []

        # === 路由：渲染器模式 vs Requests 模式 ===
        if self.use_renderer and self.renderer:
            self.logger.info("使用渲染器模式搜索 1688...")
            return self._search_with_renderer(keyword, page)

        # === 原有 Requests 模式保持不变 ===

        products = []

        # 构建搜索URL（URL编码关键词）
        if not isinstance(keyword, str):
            keyword = str(keyword)
        encoded_keyword = quote_plus(keyword)
        url = f"{self.BASE_URL}{self.SEARCH_PATH}?keywords={encoded_keyword}&page={page}"

        self.logger.info(f"搜索 1688: {keyword[:50]} (第{page}页)")

        try:
            # === 反爬虫：延迟 ===
            self.delay_manager.wait()

            # === 动态请求头 ===
            headers = {
                "User-Agent": self.ua_rotator.get(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Referer": "https://www.1688.com/",
            }

            # === 代理选择 ===
            proxies = None
            if self.single_proxy:
                proxies = self.single_proxy
            elif self.proxy_pool and self.proxy_pool.proxies:
                proxy = self.proxy_pool.get()
                if proxy:
                    proxies = {"http": proxy, "https": proxy}

            # === 发送请求（重试）===
            for attempt in range(3):
                try:
                    response = self.session.get(
                        url, 
                        headers=headers, 
                        proxies=proxies,
                        timeout=30,
                    )
                    response.raise_for_status()
                    break
                except requests.RequestException as e:
                    if attempt < 2:
                        wait = (attempt + 1) * 2 + random.uniform(0, 1)
                        self.logger.warning(f"请求失败，{wait:.1f}s后重试（第{attempt+1}次）: {e}")
                        time.sleep(wait)
                        headers["User-Agent"] = self.ua_rotator.get()
                        if self.proxy_pool and proxies:
                            proxy = self.proxy_pool.get()
                            if proxy:
                                proxies = {"http": proxy, "https": proxy}
                    else:
                        raise

            self.request_count += 1

            # === 拦截检测 ===
            if BlockDetector.is_blocked(response.text, response.status_code):
                self.block_count += 1
                self.logger.error(f"⚠️ 疑似被 1688 拦截！保存页面")
                with open(f"data/raw/blocked_1688_page{page}_{keyword[:20]}.html", "w", encoding="utf-8") as f:
                    f.write(response.text)
                return []

            # === 解析 ===
            soup = BeautifulSoup(response.text, 'html.parser')

            # 商品选择器（多模式）
            item_selectors = [
                'div[data-pid]',  # 新版
                'div[data-h5-flist] div[data-pid]',
                'div.offer-list-wrapper div[data-pid]',
                'div[class*="offer-item"]',
            ]

            items = []
            for selector in item_selectors:
                items = soup.select(selector)
                if items:
                    self.logger.debug(f"选择器 '{selector}' 找到 {len(items)} 个商品")
                    break

            if not items:
                self.logger.warning(f"未找到商品列表，保存调试页面")
                with open(f"data/raw/debug_1688_{keyword[:20]}_page{page}.html", "w", encoding="utf-8") as f:
                    f.write(response.text)
                return []

            for item in items[:30]:
                try:
                    product = self._parse_product_item(item, keyword)
                    if product:
                        products.append(product)
                except Exception as e:
                    self.logger.error(f"解析 1688 商品失败: {e}")
                    continue

            self.logger.info(f"✓ 1688 搜索完成: {keyword} - 第{page}页 - {len(products)} 个商品")

        except requests.RequestException as e:
            self.logger.error(f"1688 请求失败: {e}")
        except Exception as e:
            self.logger.error(f"1688 未知错误: {e}", exc_info=True)

        return products


    def _parse_1688_item(self, item) -> Optional[AlibabaProduct]:
        """
        解析 1688 商品 DOM 节点

        Args:
            item: BeautifulSoup 标签对象

        Returns:
            AlibabaProduct 对象（失败返回 None）
        """
        try:
            # 商品ID
            product_id = item.get('data-pid', '')
            if not product_id:
                return None

            # 标题（多选择器）
            title_selectors = [
                'div[data-spm="doffer"] a.offer-title',
                'a[data-spm="doffer"]',
                'div.title a',
                'div[class*="title"] a',
                'a[title]',
            ]

            title = ''
            for selector in title_selectors:
                el = item.select_one(selector)
                if el:
                    title = el.get('title') or el.get_text(strip=True)
                    if title:
                        break

            if not title:
                # 尝试直接获取 item 的文本
                title = item.get_text(strip=True)[:100]

            # 价格（多选择器）
            price_selectors = [
                'span[data-price]',
                'div.price span',
                'span.price',
                'em.price',
            ]

            price = 0.0
            for selector in price_selectors:
                el = item.select_one(selector)
                if el:
                    price_text = el.get('data-price') or el.get_text(strip=True)
                    try:
                        price = float(re.sub(r'[^\d.]', '', price_text))
                        break
                    except:
                        pass

            # 成交量/销量
            sales = 0
            sales_selectors = [
                'span.sale',
                'div.sale',
                'span[data-sale]',
            ]
            for selector in sales_selectors:
                el = item.select_one(selector)
                if el:
                    sales_text = el.get_text(strip=True)
                    try:
                        # 提取数字（如 "1000+" → 1000）
                        sales = int(re.sub(r'[^\d]', '', sales_text))
                        break
                    except:
                        pass

            # 商家
            shop_name = ''
            shop_selectors = [
                'div[data-nick]',
                'a.seller-name',
                'div.shop-name a',
            ]
            for selector in shop_selectors:
                el = item.select_one(selector)
                if el:
                    shop_name = el.get('data-nick') or el.get_text(strip=True)
                    if shop_name:
                        break

            # 链接
            product_url = ''
            link_selectors = [
                'a[href*="detail.1688.com"]',
                'a[href*="offer"]',
                'div[data-h5-flist] a',
            ]
            for selector in link_selectors:
                el = item.select_one(selector)
                if el:
                    product_url = el.get('href', '')
                    if product_url and not product_url.startswith('http'):
                        product_url = 'https:' + product_url if product_url.startswith('//') else 'https://www.1688.com' + product_url
                    break

            # 图片
            image_url = ''
            img_selectors = [
                'img[src*="cbu01"]',
                'img[data-src]',
                'img[src]',
            ]
            for selector in img_selectors:
                el = item.select_one(selector)
                if el:
                    image_url = el.get('data-src') or el.get('src', '')
                    if image_url and not image_url.startswith('http'):
                        image_url = 'https:' + image_url if image_url.startswith('//') else image_url
                    break

            return AlibabaProduct(
                asin=str(product_id),
                title=title.strip(),
                price=price,
                sales=sales,
                shop_name=shop_name.strip(),
                product_url=product_url,
                image_url=image_url,
                source='1688_render'
            )

        except Exception as e:
            self.logger.debug(f"商品解析异常: {e}")
            return None



    def match_amazon_product(self, amazon_title: str, amazon_category: str, 
                             amazon_price: Optional[float] = None, max_results: int = 3) -> Optional[AlibabaProduct]:
        """
        匹配 Amazon 商品到 1688 同款（高阶接口）

        Args:
            amazon_title: Amazon 商品标题
            amazon_category: Amazon 类目
            amazon_price: Amazon 价格（可选，用于过滤）
            max_results: 最大返回结果数

        Returns:
            最佳匹配的 1688 商品（或 None）
        """
        self.logger.info(f"匹配 Amazon 商品: {amazon_title[:50]}")

        # 生成搜索关键词（从 Amazon 标题提取）
        keyword = self._extract_search_keyword(amazon_title)
        self.logger.debug(f"搜索关键词: {keyword}")

        # 搜索 1688
        products = self.search_products(keyword, page=1)
        self.logger.info(f"搜索到 {len(products)} 个 1688 商品")

        if not products:
            return None

        # 使用模糊匹配器评分
        from app.utils.fuzzy_matcher import TitleMatcher
        matcher = TitleMatcher()

        best_match = None
        best_score = 0.0

        for alibaba_product in products[:max_results]:
            score = matcher.calculate_similarity(amazon_title, alibaba_product.title)

            if score > best_score:
                best_score = score
                best_match = alibaba_product

            self.logger.debug(f"  候选: {alibaba_product.title[:40]} 相似度: {score:.3f}")

        # 阈值过滤
        threshold = self.config.get('matching', {}).get('similarity_threshold', 0.6)
        if best_score >= threshold:
            self.logger.info(f"✓ 匹配成功: 相似度 {best_score:.3f}")
            return best_match
        else:
            self.logger.warning(f"✗ 匹配失败: 最高相似度 {best_score:.3f} < {threshold}")
            return None

if __name__ == "__main__":
    matcher = AlibabaMatcher(request_delay=(3, 6))

    test_title = "Pet Fountain Water Fountain for Cats and Dogs, 2.4L Stainless Steel Automatic Drinking Bowl"

    print(f"测试 Amazon 商品: {test_title[:60]}...")
    print("搜索 1688 同款中...\n")

    results = matcher.match_amazon_product(test_title, max_results=5)

    if results:
        print(f"找到 {len(results)} 个潜在匹配:\n")
        for i, r in enumerate(results, 1):
            print(f"{i}. 相似度: {r.score:.1%} | 置信度: {r.confidence}")
            print(f"   1688标题: {r.alibaba_title[:60]}...")
            print(f"   价格: ¥{r.alibaba_price or 'N/A'}")
            print(f"   链接: {r.alibaba_url[:60]}...")
            print()
    else:
        print("未找到匹配商品（可能被反爬或关键词需优化）")
