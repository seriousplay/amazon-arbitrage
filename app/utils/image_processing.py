"""
图像处理工具 - OpenCV（四层防御核心）
"""

import cv2
import numpy as np
from typing import Optional, Tuple
import sys
import random


def find_slider_by_vision(full_img: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    """Layer 2: 纯视觉检测 - 定位滑块（蓝色 HSV 分割）"""
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
        x, y, w, h = cv2.boundingRect(cnt)
        area = cv2.contourArea(cnt)
        aspect = w / h if h > 0 else 0

        if 1.5 <= aspect <= 5.0 and 200 <= area <= 15000:
            roi = full_img[y : y + h, x : x + w]
            if roi.size > 0:
                hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                blue_pixels = cv2.inRange(hsv_roi, lower_blue, upper_blue).sum()
                blue_ratio = blue_pixels / (w * h * 3) if w * h > 0 else 0
                if blue_ratio > 0.1:
                    candidates.append((x, y, w, h, area, blue_ratio))

    if candidates:
        candidates.sort(key=lambda c: c[4] * c[5], reverse=True)
        x, y, w, h, area, ratio = candidates[0]
        sys.stderr.write(f"[DEBUG] 视觉定位滑块: x={x}, y={y}, w={w}, h={h}\n")
        return (x, y, w, h)

    return None


def find_gap_advanced(bg_img: np.ndarray, slider_img: np.ndarray) -> Optional[int]:
    """高级缺口识别 - 模板匹配 + 差分法"""
    try:
        bg_gray = cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY) if len(bg_img.shape) == 3 else bg_img
        slider_gray = (
            cv2.cvtColor(slider_img, cv2.COLOR_BGR2GRAY)
            if len(slider_img.shape) == 3
            else slider_img
        )

        bg_edges = cv2.Canny(bg_gray, 50, 150)
        slider_edges = cv2.Canny(slider_gray, 50, 150)

        result = cv2.matchTemplate(bg_edges, slider_edges, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val > 0.3:
            return max_loc[0] + slider_img.shape[1] // 3

        diff = cv2.absdiff(bg_gray, slider_gray)
        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest)
            if w < h * 2 and w > 5:
                return x
    except Exception as e:
        sys.stderr.write(f"[DEBUG] 缺口识别异常: {e}\n")

    return None


def generate_realistic_trajectory(distance: int, start_x: float, start_y: float):
    """生成拟人化拖动轨迹 - 贝塞尔曲线 + 随机抖动"""
    import numpy as np

    num_points = max(15, min(40, int(distance / 3)))
    end_x = start_x + distance
    end_y = start_y

    cp1_x = start_x + distance * random.uniform(0.15, 0.25)
    cp1_y = start_y + random.uniform(-2, 2)
    cp2_x = start_x + distance * random.uniform(0.70, 0.80)
    cp2_y = start_y + random.uniform(-2, 2)

    points = []
    for t in np.linspace(0, 1, num_points):
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
        jitter_x = random.uniform(-0.3, 0.3)
        jitter_y = random.uniform(-0.3, 0.3)
        points.append((x + jitter_x, y + jitter_y, 0.01))

    return points
