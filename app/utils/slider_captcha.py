#!/usr/bin/env python3
"""
1688 滑块验证码自动破解模块
基于 OpenCV 图像识别 + 贝塞尔曲线轨迹模拟

技术栈：
- OpenCV: 缺口位置识别（边缘检测 + 模板匹配）
- NumPy: 图像数组处理
- Playwright: 浏览器自动化操作

实现步骤：
1. 检测页面是否出现滑块验证码
2. 截图并提取滑块和背景图片
3. 使用 OpenCV 计算缺口位置
4. 生成人类化拖动轨迹（贝塞尔曲线）
5. 执行拖动并通过验证

参考项目：
- Tencent-Slider-Passer-Playwright (OpenCV 模板匹配)
- casual-silva/captcha_cracking (边缘检测方案)
"""

import asyncio
import logging
import time
import os
from pathlib import Path
from typing import Optional, Tuple, List
from dataclasses import dataclass

import numpy as np
import cv2
from PIL import Image

logger = logging.getLogger(__name__)

# ========== 配置常量 ==========

# 滑块选择器（按优先级）
SLIDER_SELECTORS = [
    ".nc-lang-clear",  # 1688 常见滑块容器
    ".nc_iconfont.btn_slide",  # 滑块按钮
    "#nc_1_n1z",  # 滑块轨道
    ".nc-container",  # 滑块容器
    '[class*="slider"]',  # 任意滑块类
    '[class*="captcha"]',  # 验证码相关
    ".captcha-slider",  # 滑块验证码
    "#baxia-dialog-content",  # 阿里巴巴滑块弹窗
]

# 背景图选择器
BACKGROUND_SELECTORS = [
    ".nc-container",  # 包含背景图的容器
    ".nc_img",
    "#nc_1_n1",
    '[id*="nc"]',
]

# 临时截图目录
TEMP_DIR = Path(__file__).parent.parent.parent / "data" / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class SliderResult:
    """滑块破解结果"""

    success: bool
    distance: Optional[int] = None  # 滑动距离（像素）
    error: Optional[str] = None  # 错误信息
    attempts: int = 0  # 尝试次数


class SliderCaptchaSolver:
    """滑块验证码破解器"""

    def __init__(self, page, output_dir: Optional[str] = None):
        """
        初始化破解器

        Args:
            page: Playwright Page 对象
            output_dir: 调试图片输出目录（None=不保存）
        """
        self.page = page
        self.output_dir = Path(output_dir) if output_dir else TEMP_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 配置参数
        self.max_retries = 3  # 最大重试次数
        self.confidence_threshold = 0.8  # 模板匹配置信度

        logger.info("SliderCaptchaSolver 初始化完成")

    # ========== 步骤 1: 滑块检测 ==========

    async def detect_slider(self) -> bool:
        """
        检测页面是否包含滑块验证码

        Returns:
            True 如果检测到滑块元素
        """
        for selector in SLIDER_SELECTORS:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    logger.info(f"检测到滑块元素: {selector}")
                    return True
            except Exception as e:
                continue

        # 检查页面是否包含验证码相关文本
        content = await self.page.content()
        captcha_keywords = ["验证", "滑块", "拖动", "captcha", "slider", "verify"]
        if any(kw in content.lower() for kw in captcha_keywords):
            logger.info("页面内容包含验证码关键词")
            return True

        return False

    # ========== 步骤 2: 截图与元素提取 ==========

    async def capture_slider_images(self) -> Optional[Tuple[np.ndarray, np.ndarray, dict]]:
        """
        截取滑块和背景图片

        Returns:
            (bg_image, slider_image, element_info) 或 None
        """
        try:
            # 方法 A: 通过选择器定位元素并裁剪
            for bg_selector in BACKGROUND_SELECTORS:
                bg_elem = await self.page.query_selector(bg_selector)
                if bg_elem:
                    # 截图背景元素
                    bg_path = self.output_dir / "bg_element.png"
                    await bg_elem.screenshot(path=str(bg_path))

                    # 查找滑块元素
                    slider_elem = None
                    for s_sel in SLIDER_SELECTORS:
                        slider_elem = await self.page.query_selector(s_sel)
                        if slider_elem:
                            break

                    if slider_elem:
                        slider_path = self.output_dir / "slider_element.png"
                        await slider_elem.screenshot(path=str(slider_path))

                        # 读取为 numpy 数组
                        bg_img = cv2.imread(str(bg_path))
                        slider_img = cv2.imread(str(slider_path))

                        if bg_img is not None and slider_img is not None:
                            logger.info(
                                f"成功截取背景图 {bg_img.shape} 和滑块图 {slider_img.shape}"
                            )

                            # 获取元素位置信息（用于后续定位）
                            box = await bg_elem.bounding_box()
                            return bg_img, slider_img, {"box": box}

            # 方法 B: 全屏截图 + 模板匹配定位滑块
            logger.info("使用全屏截图方式")
            full_path = self.output_dir / "fullpage.png"
            await self.page.screenshot(path=str(full_path), full_page=True)
            full_img = cv2.imread(str(full_path))

            if full_img is not None:
                # TODO: 在全屏图中通过模板匹配找到滑块位置
                # 暂时返回 None，需要额外实现
                logger.warning("全屏截图模式暂未实现完整定位")
                return None

        except Exception as e:
            logger.error(f"截图失败: {e}", exc_info=True)

        return None

    # ========== 步骤 3: OpenCV 缺口识别 ==========

    @staticmethod
    def find_gap_position(bg_img: np.ndarray, slider_img: np.ndarray) -> int:
        """
        使用 OpenCV 找到缺口位置

        算法：边缘检测 + 模板匹配

        Args:
            bg_img: 背景图（带缺口）
            slider_img: 滑块图（缺口的形状）

        Returns:
            缺口左边缘的 x 坐标（像素距离）
        """
        # 转换为灰度图
        if len(bg_img.shape) == 3:
            bg_gray = cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY)
        else:
            bg_gray = bg_img

        if len(slider_img.shape) == 3:
            slider_gray = cv2.cvtColor(slider_img, cv2.COLOR_BGR2GRAY)
        else:
            slider_gray = slider_img

        # 边缘检测（Canny）
        bg_edges = cv2.Canny(bg_gray, 50, 150)
        slider_edges = cv2.Canny(slider_gray, 50, 150)

        # 模板匹配（寻找滑块在背景中的位置）
        # 使用 TM_CCOEFF_NORMED 归一化相关系数匹配
        result = cv2.matchTemplate(bg_edges, slider_edges, cv2.TM_CCOEFF_NORMED)

        # 获取最佳匹配位置
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        logger.info(f"模板匹配置信度: {max_val:.3f}, 位置: {max_loc}")

        if max_val < 0.5:
            logger.warning(f"匹配置信度过低: {max_val:.3f}，可能识别错误")

        # max_loc 是滑块的左上角坐标
        gap_x = max_loc[0]

        return gap_x

    @staticmethod
    def find_gap_by_contours(bg_img: np.ndarray, slider_img: np.ndarray) -> int:
        """
        替代方案：轮廓检测法

        步骤：
        1. 计算背景图和滑块图的差异
        2. 二值化 + 边缘检测
        3. 寻找轮廓，确定缺口位置
        """
        # 转为灰度
        bg_gray = cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY) if len(bg_img.shape) == 3 else bg_img
        slider_gray = (
            cv2.cvtColor(slider_img, cv2.COLOR_BGR2GRAY)
            if len(slider_img.shape) == 3
            else slider_img
        )

        # 差值（背景 - 滑块 = 缺口区域）
        diff = cv2.absdiff(bg_gray, slider_gray)

        # 二值化
        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)

        # 形态学操作（去噪）
        kernel = np.ones((3, 3), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        # 寻找轮廓
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            # 取最大轮廓（缺口通常是最大的）
            largest = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest)
            logger.info(f"轮廓检测: x={x}, w={w}")
            return x

        return 0

    # ========== 步骤 4: 轨迹生成（贝塞尔曲线） ==========

    @staticmethod
    def generate_bezier_trajectory(
        distance: int, start_x: int = 0, start_y: int = 0, num_points: int = 20
    ) -> List[Tuple[int, int]]:
        """
        生成贝塞尔曲线拖动轨迹

        模拟人类拖动特征：
        - 先加速后减速（S形曲线）
        - 添加微小随机抖动
        - 起始和结束位置有轻微回弹

        Args:
            distance: 总滑动距离（像素）
            start_x: 起始 x 坐标
            start_y: 起始 y 坐标
            num_points: 轨迹点数量（越多越平滑）

        Returns:
            [(x1, y1), (x2, y2), ...] 轨迹点列表
        """
        # 控制点（决定曲线形状）
        # P0 = 起点, P1 = 控制点1, P2 = 控制点2, P3 = 终点

        # 模拟人类行为：开始慢，中间快，结束慢
        # 使用三次贝塞尔曲线

        # 终点
        end_x = start_x + distance
        end_y = start_y

        # 控制点（经验值）
        # CP1: 10-20% 处，轻微向上偏移（模拟加速度）
        cp1_x = start_x + distance * 0.2
        cp1_y = start_y - random.uniform(1, 3)  # 轻微上移

        # CP2: 70-80% 处，轻微向下偏移（模拟减速度）
        cp2_x = start_x + distance * 0.75
        cp2_y = start_y + random.uniform(1, 3)  # 轻微下移

        points = []
        for t in np.linspace(0, 1, num_points):
            # 三次贝塞尔公式
            x = (
                (1 - t) ** 3 * start_x
                + 3 * (1 - t) ** 2 * t * cp1_x
                + 3 * (1 - t) * t**2 * cp2_x
                + t**3 * end_x
            )
            y = (
                (1 - t) ** 3 * start_y
                + 3 * (1 - t) ** 2 * t * cp1_y
                + 3 * (1 - t) * t**2 * cp2_y
                + t**3 * end_y
            )

            # 添加微小随机抖动（模拟手抖）
            jitter = random.uniform(-0.5, 0.5)
            x += jitter
            y += jitter

            points.append((int(x), int(y)))

        logger.debug(
            f"生成轨迹: 起点({start_x},{start_y}) → 终点({end_x},{end_y}), {len(points)} 个点"
        )
        return points

    @staticmethod
    def generate_human_like_trajectory(
        distance: int, start_x: int = 0, start_y: int = 0
    ) -> List[Tuple[int, int]]:
        """
        更复杂的人类轨迹模拟（带速度曲线）

        使用缓动函数模拟真实的加速-减速过程
        """
        # 参数
        num_points = random.randint(30, 50)  # 轨迹点数量
        pause_at_start = random.uniform(0.1, 0.3)  # 起始停顿
        pause_at_end = random.uniform(0.1, 0.3)  # 结束停顿

        points = []

        # 初始停顿（不移动）
        for _ in range(int(pause_at_start * 10)):
            points.append((start_x, start_y))

        # 移动阶段
        for i in range(num_points):
            t = i / (num_points - 1)

            # 使用 ease-in-out 曲线
            # f(t) = 3t² - 2t³ (平滑的 S 形)
            progress = 3 * t**2 - 2 * t**3

            # 当前距离
            current_dist = distance * progress

            # 添加随机抖动（越接近目标抖动越小）
            jitter = random.uniform(-2, 2) * (1 - progress)

            x = start_x + int(current_dist) + int(jitter)
            y = start_y + random.randint(-1, 1)  # y 轴轻微波动

            points.append((x, y))

        # 结束停顿
        for _ in range(int(pause_at_end * 10)):
            points.append((start_x + distance, start_y))

        return points

    # ========== 步骤 5: 执行拖动 ==========

    async def perform_slide(
        self,
        slider_selector: str,
        distance: int,
        trajectory: Optional[List[Tuple[int, int]]] = None,
    ) -> bool:
        """
        执行滑块拖动操作

        Args:
            slider_selector: 滑块元素选择器
            distance: 滑动距离
            trajectory: 自定义轨迹（None=自动生成）

        Returns:
            True 如果拖动成功
        """
        try:
            # 定位滑块元素
            slider = await self.page.query_selector(slider_selector)
            if not slider:
                logger.error(f"未找到滑块元素: {slider_selector}")
                return False

            # 获取滑块边界框
            box = await slider.bounding_box()
            if not box:
                logger.error("无法获取滑块位置")
                return False

            start_x = box["x"] + box["width"] / 2
            start_y = box["y"] + box["height"] / 2

            logger.info(f"滑块位置: x={start_x:.1f}, y={start_y:.1f}, 距离={distance}px")

            # 生成轨迹
            if trajectory is None:
                # 使用贝塞尔曲线
                trajectory = self.generate_bezier_trajectory(
                    distance=distance, start_x=int(start_x), start_y=int(start_y)
                )

            # 执行拖动（Playwright mouse API）
            await self.page.mouse.move(int(start_x), int(start_y))
            await self.page.mouse.down()

            # 逐步移动
            for idx, (x, y) in enumerate(trajectory):
                await self.page.mouse.move(x, y)
                # 随机延迟（模拟人类操作间隔 10-50ms）
                if idx < len(trajectory) - 1:
                    await asyncio.sleep(random.uniform(0.01, 0.05))

            await self.page.mouse.up()

            # 等待验证结果
            await asyncio.sleep(random.uniform(0.5, 1.0))

            logger.info(f"拖动完成，共 {len(trajectory)} 个轨迹点")
            return True

        except Exception as e:
            logger.error(f"拖动失败: {e}", exc_info=True)
            return False

    # ========== 主流程 ==========

    async def solve(
        self, slider_selector: Optional[str] = None, bg_selector: Optional[str] = None
    ) -> SliderResult:
        """
        主流程：自动检测并破解滑块验证码

        Args:
            slider_selector: 滑块选择器（None=自动检测）
            bg_selector: 背景选择器（None=自动检测）

        Returns:
            SliderResult 结果对象
        """
        logger.info("开始滑块验证码破解流程")

        for attempt in range(1, self.max_retries + 1):
            logger.info(f"尝试 #{attempt}/{self.max_retries}")

            try:
                # 1. 检测滑块
                if not await self.detect_slider():
                    logger.info("未检测到滑块验证码")
                    return SliderResult(success=True, distance=0)

                # 2. 截图
                capture_result = await self.capture_slider_images()
                if capture_result is None:
                    error = "截图失败"
                    logger.error(error)
                    return SliderResult(success=False, error=error, attempts=attempt)

                bg_img, slider_img, elem_info = capture_result

                # 保存调试图片
                cv2.imwrite(str(self.output_dir / f"bg_attempt{attempt}.png"), bg_img)
                cv2.imwrite(str(self.output_dir / f"slider_attempt{attempt}.png"), slider_img)

                # 3. 识别缺口位置
                gap_x = self.find_gap_position(bg_img, slider_img)
                logger.info(f"识别缺口位置: x={gap_x}px")

                # 4. 计算滑动距离
                # 通常需要加上滑块的宽度（因为匹配到的是滑块左边缘，需要移动到缺口左边缘）
                slider_width = slider_img.shape[1]
                distance = max(0, gap_x - slider_width // 2)
                logger.info(f"计算滑动距离: {distance}px (gap={gap_x}, slider_w={slider_width})")

                # 5. 执行拖动
                s_selector = slider_selector or SLIDER_SELECTORS[0]
                success = await self.perform_slide(s_selector, distance)

                if success:
                    logger.info(f"滑块破解成功！尝试 #{attempt}")
                    return SliderResult(success=True, distance=distance, attempts=attempt)
                else:
                    logger.warning(f"尝试 #{attempt} 失败，重试中...")

            except Exception as e:
                logger.error(f"尝试 #{attempt} 异常: {e}", exc_info=True)

        return SliderResult(
            success=False, error=f"达到最大重试次数 ({self.max_retries})", attempts=self.max_retries
        )

    async def solve_with_retry(self, **kwargs) -> SliderResult:
        """兼容旧调用方式"""
        return await self.solve(**kwargs)


# ========== 便捷函数 ==========


async def bypass_slider(page, output_dir: str = None) -> bool:
    """
    便捷函数：快速绕过滑块验证码

    Args:
        page: Playwright Page 对象
        output_dir: 调试图片目录

    Returns:
        True 如果成功绕过
    """
    solver = SliderCaptchaSolver(page, output_dir)
    result = await solver.solve()
    return result.success
