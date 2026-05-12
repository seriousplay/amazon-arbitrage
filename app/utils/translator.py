"""
Amazon 标题 → 1688 中文搜索词 转换器
提取核心产品词并翻译为中文，提升 1688 搜索精准度

架构说明：
- TERM_MAP 从 data/translations/en_zh_terms.json 加载（438 条英中映射）
- STOP_WORDS 保留在代码中（稳定的小型词表）
- BRAND_PATTERNS 保留在代码中（正则表达式列表）
"""

import json
import re
from pathlib import Path

# ─── 数据文件路径 ──────────────────────────────────
DATA_DIR = Path(__file__).parent.parent.parent / "data"
TERM_MAP_PATH = DATA_DIR / "translations" / "en_zh_terms.json"


# ─── 英→中产品词库（从 JSON 加载）────────────────


def _load_term_map() -> dict:
    """从 JSON 文件加载翻译词表"""
    try:
        with open(TERM_MAP_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("翻译词表格式错误：应为字典")
            return data
    except FileNotFoundError:
        import logging

        logging.warning(f"翻译词表文件不存在：{TERM_MAP_PATH}，使用空词表")
        return {}
    except json.JSONDecodeError as e:
        import logging

        logging.error(f"翻译词表 JSON 解析失败：{e}")
        return {}


TERM_MAP = _load_term_map()

# 品牌词（不需翻译，1688 也可识别）
BRAND_PATTERNS = [
    r"\b(amazon basics|amazonbasics)\b",
    r"\b(purina|pedigree|royal canin|hill's|blue buffalo|taste of the wild)\b",
    r"\b(frisco|kONG|nerf|chuckit|outward hound)\b",
    r"\b(arm & hammer|fresh step|tidy cats|dr elsey)\b",
    r"\b(furminator|hertzko|JW pet|petmate|midwest)\b",
]

# 无意义词
STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "for",
    "of",
    "in",
    "on",
    "to",
    "with",
    "by",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "it",
    "its",
    "that",
    "this",
    "these",
    "those",
    "pack",
    "count",
    "ounce",
    "oz",
    "lb",
    "lbs",
    "pound",
    "inch",
    "inches",
    "cm",
    "mm",
    "size",
    "color",
    "new",
    "best",
    "top",
    "premium",
    "original",
}


def extract_keywords(title: str) -> list:
    """从 Amazon 标题提取核心产品词（英文）"""
    title_lower = title.lower()
    # 移除括号和标点
    title_clean = re.sub(r"\([^)]*\)", "", title_lower)
    title_clean = re.sub(r"\[[^\]]*\]", "", title_clean)
    title_clean = re.sub(r"[,;:!.\"']", " ", title_clean)

    # 分词（按空格和连字符拆分）
    raw_words = re.split(r"[\s-]+", title_clean)
    keywords = [w.strip() for w in raw_words if len(w.strip()) >= 2 and w.strip() not in STOP_WORDS]

    # 多词短语匹配（如 "instant film", "stainless steel"）
    phrases = []
    for phrase in sorted(TERM_MAP.keys(), key=lambda x: -len(x)):  # 长词优先
        if " " in phrase and phrase in title_lower:
            phrases.append(phrase)
            # 标记组成短语的单词已使用
            for word in phrase.split():
                if word in keywords:
                    keywords.remove(word)

    # 去重：短语优先，单个词补充
    seen = set(phrases)
    result = phrases.copy()
    for kw in keywords:
        if kw not in seen and kw in TERM_MAP:
            result.append(kw)
            seen.add(kw)

    return result[:10]


def to_chinese(title: str) -> str:
    """Amazon 标题 → 简短中文搜索词（用于 1688 搜索）"""
    # 1. 优先：标题本身包含中文，直接提取
    cn_chars = re.findall(r"[一-鿿]+", title)
    if cn_chars:
        cn_text = " ".join(cn_chars)
        if len(cn_text) >= 3:
            return cn_text[:60]

    # 2. 其次：翻译英文关键词
    keywords = extract_keywords(title)
    cn_words = []
    for kw in keywords:
        if kw in TERM_MAP:
            cn_words.append(TERM_MAP[kw])

    seen = set()
    result = []
    for w in cn_words:
        if w not in seen:
            result.append(w)
            seen.add(w)

    # 3. 回退：用英文原文前几个词（1688 也能搜英文）
    if not result:
        en_fallback = [kw for kw in keywords if kw not in STOP_WORDS][:4]
        return " ".join(en_fallback) if en_fallback else " ".join(title.split()[:3])

    return " ".join(result[:6])


def translate_detail(title: str) -> dict:
    """返回翻译详情（原始 → 关键词 → 中文搜索词）"""
    return {
        "original": title,
        "keywords": extract_keywords(title),
        "chinese": to_chinese(title),
    }
