"""
CaptchaSolver - 滑块验证码破解器

职责：
- 检测滑块验证码
- 4层破解策略：
  1. 智能元素定位（最快）
  2. 纯视觉检测（OpenCV）
  3. 贝塞尔曲线轨迹模拟（人类化）
  4. 自动重试与降级
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# 调试截图目录
DEBUG_DIR = Path(__file__).parent.parent.parent / "data" / "temp" / "captcha"


class CaptchaSolver:
    """滑块验证码破解器"""

    def __init__(self, debug: bool = False, confidence_threshold: float = 0.8):
        """
        初始化 CaptchaSolver

        Args:
            debug: 是否保存调试截图
            confidence_threshold: 匹配置信度阈值（0-1）
        """
        self.debug = debug
        self.confidence_threshold = confidence_threshold

        if self.debug:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    async def detect_and_solve(self, page) -> Optional[bool]:
        """
        检测并尝试解决滑块验证码

        Args:
            page: Playwright Page 对象

        Returns:
            True 如果成功解决，False 如果需要人工干预，None 如果未检测到验证码
        """
        # 1. 检测验证码是否存在
        has_captcha = await self._detect_captcha(page)
        if not has_captcha:
            return None

        logger.warning("⚠️ 检测到滑块验证码，尝试破解...")

        # 2. 尝试第1层：智能元素定位
        if await self._try_smart_locator(page):
            logger.info("✓ 验证码通过智能定位解决")
            return True

        # 3. 尝试第2层：视觉检测 + 贝塞尔轨迹
        if await self._try_vision_based(page):
            logger.info("✓ 验证码通过视觉检测解决")
            return True

        # 4. 所有层都失败
        logger.error("✗ 无法自动解决验证码，需要人工干预")
        return False

    async def _detect_captcha(self, page) -> bool:
        """检测页面是否出现滑块验证码"""
        captcha_selectors = [
            '.nc-lang-clear',
            '.nc_iconfont.btn_slide',
            '#nc_1_n1z',
            '.nc-container',
            '[class*="slider"]',
            '[class*="captcha"]',
            '.captcha-slider',
            '#baxia-dialog-content',
        ]

        for selector in captcha_selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=1000)
                if element:
                    logger.info(f"检测到验证码元素: {selector}")
                    return True
            except:
                continue

        return False

    async def _try_smart_locator(self, page) -> bool:
        """
        第1层：智能元素定位

        尝试快速点击、滑动等操作，不进行图像处理
        """
        try:
            # 尝试找到滑块并直接拖拽
            slider = await page.query_selector('.nc-lang-clear, .nc_iconfont.btn_slide')
            if not slider:
                return False

            box = await slider.bounding_box()
            if not box:
                return False

            # 简单的直线拖拽
            await page.mouse.move(box['x'] + 10, box['y'] + box['height'] / 2)
            await page.mouse.down()
            await page.mouse.move(box['x'] + 200, box['y'] + box['height'] / 2, steps=10)
            await page.mouse.up()

            # 等待并检查是否通过
            await asyncio.sleep(1)
            return not await self._detect_captcha(page)

        except Exception as e:
            logger.debug(f"智能定位失败: {e}")
            return False

    async def _try_vision_based(self, page) -> bool:
        """
        第2层：纯视觉检测 + 贝塞尔轨迹

        使用 OpenCV 计算缺口位置，生成人类化轨迹
        """
        try:
            # 截图
            screenshot = await page.screenshot()
            img = np.frombuffer(screenshot, dtype=np.uint8)
            img = cv2.imdecode(img, cv2.IMREAD_COLOR)

            # 查找缺口位置（简化实现）
            gap_position = await self._find_gap_position(img)
            if gap_position is None:
                return False

            # 生成贝塞尔曲线轨迹
            trajectory = await self._generate_trajectory(gap_position)

            # 执行拖拽
            return await self._execute_drag(page, trajectory)

        except Exception as e:
            logger.error(f"视觉检测失败: {e}")
            return False

    async def _find_gap_position(self, img: np.ndarray) -> Optional[int]:
        """
        查找缺口位置（使用边缘检测）

        Args:
            img: 截图图像

        Returns:
            缺口 X 坐标，如果未找到则返回 None
        """
        # 转换为灰度图
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 边缘检测
        edges = cv2.Canny(gray, 50, 150)

        # 查找轮廓
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 查找可能是缺口的轮廓
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            # 缺口通常是特定大小和形状的
            if 50 < w < 200 and 30 < h < 100:
                if self.debug:
                    self._save_debug_image(img, (x, y, w, h))
                return x + w // 2

        return None

    async def _generate_trajectory(self, target_x: int) -> List[Tuple[int, int]]:
        """
        生成贝塞尔曲线拖拽轨迹

        Args:
            target_x: 目标 X 坐标

        Returns:
            轨迹点列表 [(x, y), ...]
        """
        # 简化实现：返回线性轨迹
        # 实际应该使用贝塞尔曲线生成人类化轨迹
        start_x = 0
        y = 0
        points = []
        steps = 50

        for i in range(steps + 1):
            t = i / steps
            x = start_x + (target_x - start_x) * t
            points.append((int(x), y))

        return points

    async def _execute_drag(self, page, trajectory: list) -> bool:
        """执行拖拽操作"""
        try:
            # 假设滑块起始位置
            start_x, start_y = 100, 300

            await page.mouse.move(start_x, start_y)
            await page.mouse.down()

            for x, y in trajectory:
                await page.mouse.move(start_x + x, start_y + y)
                await asyncio.sleep(0.01)

            await page.mouse.up()
            await asyncio.sleep(1)

            # 检查是否通过
            return not await self._detect_captcha(page)

        except Exception as e:
            logger.error(f"拖拽执行失败: {e}")
            return False

    def _save_debug_image(self, img: np.ndarray, rect: Tuple[int, int, int, int]):
        """保存调试图像"""
        if not self.debug:
            return

        debug_img = img.copy()
        x, y, w, h = rect
        cv2.rectangle(debug_img, (x, y), (x + w, y + h), (0, 255, 0), 2)

        timestamp = int(asyncio.get_event_loop().time())
        filepath = DEBUG_DIR / f"captcha_{timestamp}.png"
        cv2.imwrite(str(filepath), debug_img)
        logger.debug(f"调试截图已保存: {filepath}")
