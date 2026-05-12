"""
Amazon 类目路径 → 1688 精准搜索词 映射
基于 Amazon 自有类目体系，远比关键词翻译可靠

架构说明：
- CATEGORY_MAP 从 data/categories/category_mapping.json 加载（355 条映射）
- 支持配置自定义路径（通过环境变量 CATEGORY_MAP_PATH）
"""

import json
import os
from pathlib import Path
from typing import Dict


# ─── 数据文件路径 ──────────────────────────────────
def _get_category_map_path() -> Path:
    """获取 CATEGORY_MAP 文件路径（支持环境变量覆盖）"""
    env_path = os.getenv("CATEGORY_MAP_PATH")
    if env_path:
        return Path(env_path)
    return Path(__file__).parent.parent.parent / "data" / "categories" / "category_mapping.json"


CATEGORY_MAP_PATH = _get_category_map_path()


# ─── Amazon 叶子类目 → 1688 搜索词（从 JSON 加载）────


def _load_category_map() -> Dict[str, str]:
    """从 JSON 文件加载类目映射"""
    try:
        with open(CATEGORY_MAP_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("类目映射格式错误：应为字典")
            return data
    except FileNotFoundError:
        import logging

        logging.warning(f"类目映射文件不存在：{CATEGORY_MAP_PATH}，使用空映射")
        return {}
    except json.JSONDecodeError as e:
        import logging

        logging.error(f"类目映射 JSON 解析失败：{e}")
        return {}


CATEGORY_MAP = _load_category_map()


def category_to_search(category_path: str, product_title: str = "") -> str:
    """从 Amazon 类目路径提取最精准的 1688 搜索词"""
    if not category_path:
        return ""

    # 按 > 拆分，取最后两级（最具体的叶子类目）
    parts = [p.strip().lower() for p in category_path.split(">")]
    if not parts:
        return ""

    # 优先匹配叶子类目
    leaf = parts[-1]
    if leaf in CATEGORY_MAP:
        return CATEGORY_MAP[leaf]

    # 尝试倒数第二级
    if len(parts) >= 2 and parts[-2] in CATEGORY_MAP:
        return CATEGORY_MAP[parts[-2]]

    # 尝试任意匹配
    for p in reversed(parts):
        if p in CATEGORY_MAP:
            return CATEGORY_MAP[p]
        # 部分匹配
        for k, v in CATEGORY_MAP.items():
            if k in p or p in k:
                return v

    return ""


def get_supported_categories() -> list:
    """获取支持的类目列表"""
    return list(CATEGORY_MAP.keys())


def normalize_category(category: str) -> str:
    """标准化类目名称（小写、去除空白）"""
    if not category:
        return ""
    return category.strip().lower()
