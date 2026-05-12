#!/usr/bin/env python3
"""
宠物用品跨语言模糊匹配器
Amazon BSR 商品 ↔ 1688 同款商品匹配

策略：英文词 → 中文同义词映射 + 多维加权相似度
"""

import re
import jieba

# 在模块加载时注册宠物用品专有词汇（防止 jieba 错误切分）
_custom_terms = [
    "耐咬",
    "强力咀嚼",
    "发声器",
    "自动饮水",
    "不锈钢",
    "活水器",
    "猫砂盆",
    "带盖",
    "封闭式",
    "大型犬",
    "小型犬",
    "中型犬",
    "宠物床",
    "猫爬架",
    "猫抓板",
    "狗咬胶",
    "磨牙棒",
    "宠物食碗",
    "航空箱",
    "胸背带",
    "牵引绳",
    "宠物包",
    "尿垫",
    "除臭",
    "饮水机",
    "食碗",
    "砂盆",
    "宠物窝",
]
for _term in _custom_terms:
    jieba.add_word(_term, freq=1000, tag="n")

from dataclasses import dataclass
from typing import Dict, Tuple, Optional
from thefuzz import fuzz

# ========== 数据结构 ==========


@dataclass
class MatchResult:
    """匹配结果"""

    score: float
    strategy: str
    confidence: str  # high / medium / low
    details: Optional[Dict] = None


# ========== 匹配器核心类 ==========


class FuzzyMatcher:
    """
    跨语言模糊匹配器

    工作流程：
    1. 文本标准化（英文词 → 中文同义词 + 中文分词）
    2. 多维度相似度计算（Jaccard + 编辑距离 + 数字 + 规格）
    3. 加权融合 + 惩罚机制
    """

    def __init__(self, language: str = "zh"):
        self.language = language

        # === 宠物用品英中同义词映射（扩展 200+ 词条） ===
        # === 从 JSON 加载词典数据 ===

        def _load_json(filename: str):
            """加载 JSON 数据文件"""
            import json
            from pathlib import Path

            file_path = Path(__file__).parent.parent.parent / "data" / "matcher" / filename
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except FileNotFoundError:
                import logging

                logging.warning(f"词典文件不存在：{file_path}")
                return {}
            except json.JSONDecodeError as e:
                import logging

                logging.error(f"词典 JSON 解析失败：{e}")
                return {}

        # 宠物用品英中同义词映射（从 JSON 加载）
        self.pet_synonyms = _load_json("pet_synonyms.json")

        # 英文词形变化映射（从 JSON 加载）
        self.en_variations = _load_json("en_variations.json")

        # 语义归一化映射（从 JSON 加载）
        self.semantic_norm = _load_json("semantic_norm.json")

        # 停用词（从 JSON 加载）
        stop_words_en_list = _load_json("stop_words_en.json")
        self.stop_words_en = (
            set(stop_words_en_list) if isinstance(stop_words_en_list, list) else set()
        )

        stop_words_zh_list = _load_json("stop_words_zh.json")
        self.stop_words_zh = (
            set(stop_words_zh_list) if isinstance(stop_words_zh_list, list) else set()
        )

        # 扩展停用词（营销词、通用词）
        # 加载宠物用品专有词汇（防止 jieba 错误切分）
        # 这些词在中文标题中是复合概念，不应拆为单字
        custom_terms = [
            # 核心复合词（防止 jieba 错误切分）
            "耐咬",
            "强力咀嚼",
            "发声器",
            "自动饮水",
            "自动饮水器",
            "不锈钢",
            "活水器",
            "猫砂盆",
            "带盖",
            "封闭式",
            "大型犬",
            "小型犬",
            "中型犬",
            "宠物床",
            "猫爬架",
            "猫抓板",
            "狗咬胶",
            "磨牙棒",
            "宠物食碗",
            "航空箱",
            "胸背带",
            "牵引绳",
            "宠物包",
            "尿垫",
            "除臭",
            # 补充
            "宠物",
            "食碗",
            "碗",
            "饮水",
            "发声",
            "球",
            "猫",
            "狗",  # 常见单字词强制保留
            "互动",
            "娱乐",
            "自动",
            "智能",
            "感应",
        ]
        for term in custom_terms:
            jieba.add_word(term, freq=1000, tag="n")

        # 英文词形变化映射（自动归一化）
        self.en_variations = {
            # 复数形式
            "chewers": "chewer",
            "toys": "toy",
            "bowls": "bowl",
            "fountains": "fountain",
            "boxes": "box",
            "litters": "litter",
            "brushes": "brush",
            "collars": "collar",
            "harnesses": "harness",
            "leashes": "leash",
            "beds": "bed",
            "mats": "mat",
            "pads": "pad",
            "carriers": "carrier",
            "crates": "crate",
            "balls": "ball",
            "bones": "bone",
            "sticks": "stick",
            "chews": "chew",
            "squeakers": "squeaker",
            "bones": "bone",
            # 现在分词/动词形式
            "chewing": "chew",
            "squeaking": "squeak",
            # 所有格/形容词
            "pet": "pet",  # 本身不变
        }
        self.stop_words_en = {
            "the",
            "a",
            "an",
            "for",
            "with",
            "and",
            "or",
            "of",
            "in",
            "on",
            "new",
            "best",
            "official",
            "original",
            "genuine",
            "pack",
            "set",
            "count",
            "pc",
            "pcs",
            "x",
            "premium",
            "quality",
            "heavy",
            "duty",
            "pro",
            "professional",
            "advanced",
            "ultimate",
            "plus",
            "ultra",
            "deluxe",
            "upgraded",
            "version",
            "edition",
            "collection",
            "2024",
            "2025",
        }
        self.stop_words_zh = {
            "新款",
            "正品",
            "官方",
            "原装",
            "包邮",
            "特价",
            "促销",
            "套装",
            "清仓",
            "限时",
            "折扣",
            "特惠",
            "爆款",
            "热销",
            "推荐",
            "畅销",
            "个",
            "只",
            "条",
            "袋",
            "盒",
            "箱",
            "件",
            "套",
            "支",
            "毫升",
            "克",
            "公斤",
            "斤",
            "升",
            "米",
            "厘米",
            "毫米",
        }

        # === 语义归一化映射：同义词 → 规范词 ===
        # 目的：减少词集大小，提升 Jaccard 相似度
        self.semantic_norm = {
            # === 宠物类型归一化 ===
            "狗": "狗",
            "狗狗": "狗",
            "犬类": "狗",
            "宠物狗": "狗",
            "犬": "狗",
            "大型犬": "狗",
            "小型犬": "狗",
            "中型犬": "狗",
            "猫": "猫",
            "猫咪": "猫",
            "宠物猫": "猫",
            "feline": "猫",
            # '宠物': '宠物',  # 保留原词（避免过度归一化）
            # === 功能特性归一化 ===
            "耐咬": "耐咬",
            "强力咀嚼": "耐咬",
            "咀嚼": "耐咬",
            "咬嚼": "耐咬",
            "啃咬": "耐咬",
            "发声": "发声",
            "发声器": "发声",
            "吱吱响": "发声",
            "squeaky": "发声",
            "互动": "互动",
            "交互": "互动",
            "自动": "自动",
            "智能": "自动",
            "感应": "自动",
            "饮水": "饮水",
            "活水": "饮水",
            "循环": "饮水",
            "除臭": "除臭",
            "防臭": "除臭",
            "祛味": "除臭",
            "防水": "防水",
            "防漏": "防水",
            "防湿": "防水",
            "防滑": "防滑",
            "可调节": "可调节",
            "调节": "可调节",
            "伸缩": "可调节",
            "可折叠": "可折叠",
            "折叠": "可折叠",
            "便携": "便携",
            "耐用": "耐用",
            "耐咬": "耐用",
            "加固": "耐用",
            "结实": "耐用",
            "柔软": "柔软",
            "舒适": "柔软",
            "静音": "静音",
            "无声": "静音",
            "低噪音": "静音",
            # === 材质归一化 ===
            "不锈钢": "不锈钢",
            "不锈": "不锈钢",
            "钢": "不锈钢",
            "钢铁": "不锈钢",
            "金属": "不锈钢",
            "合金": "不锈钢",
            "塑料": "塑料",
            "塑胶": "塑料",
            "树脂": "塑料",
            "棉": "棉",
            "纯棉": "棉",
            "棉质": "棉",
            "抓绒": "绒",
            "绒": "绒",
            "毛绒": "绒",
            "尼龙": "尼龙",
            "橡胶": "橡胶",
            "硅胶": "硅胶",
            "皮革": "皮革",
            "织物": "织物",
            "网眼": "网眼",
            # === 容器类归一化 ===
            "碗": "碗",
            "食盆": "碗",
            "食碗": "碗",
            "饭盆": "碗",
            "砂盆": "砂盆",
            "猫砂盆": "砂盆",
            "猫厕所": "砂盆",
            "航空箱": "箱",
            "托运箱": "箱",
            "笼子": "箱",
            # === 复合词归一化 ===
            "饮水机": "饮水",
            "自动饮水": "饮水",
            "自动饮水器": "饮水",
            "活水器": "饮水",
            "食碗": "碗",
            "饭盆": "碗",
            "宠物食碗": "碗",
            "碗": "碗",
            "猫砂盆": "砂盆",
            "猫厕所": "砂盆",
            "发声球": "发声 球",
            "宠物玩具": "玩具",
            "耐咬玩具": "耐咬 玩具",
            "磨牙棒": "耐咬 玩具",
            "狗咬胶": "耐咬 玩具",
            "互动": "互动",  # 保留
            "娱乐": "娱乐",
        }

    def _normalize_text(self, text: str) -> str:
        """
        文本标准化：中英文混合 + 宠物用品同义词扩展
        策略：英文词完全替换为同义词中文词，避免跨语言编辑距离惩罚
        改进：支持英文词组匹配（2-gram），保留有意义的原始中文
        """
        if not text:
            return ""

        text = text.lower().strip()

        # 分词：英文词、数字、中文块
        tokens = re.findall(r"[a-zA-Z]+|\d+\.?\d*|[^a-zA-Z\s]+", text)

        keywords = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if re.match(r"^[a-zA-Z]+$", token):  # 英文词
                # 词形还原（复数→单数）
                base_form = token
                if token in self.en_variations:
                    base_form = self.en_variations[token]

                # 优先匹配词组（2-gram）
                if i + 1 < len(tokens) and re.match(r"^[a-zA-Z]+$", tokens[i + 1]):
                    next_base = tokens[i + 1]
                    if tokens[i + 1] in self.en_variations:
                        next_base = self.en_variations[tokens[i + 1]]
                    bigram = f"{base_form} {next_base}"
                    if bigram in self.pet_synonyms:
                        keywords.extend(self.pet_synonyms[bigram].split())
                        i += 2
                        continue

                # 单字匹配（优先基础形式）
                if base_form in self.pet_synonyms:
                    keywords.extend(self.pet_synonyms[base_form].split())
                elif token in self.pet_synonyms:
                    keywords.extend(self.pet_synonyms[token].split())
                i += 1
            elif re.match(r"^\d+\.?\d*$", token):  # 数字
                keywords.append(token)
                i += 1
            else:  # 中文块
                cn_words = jieba.lcut(token)
                for w in cn_words:
                    if w and w not in self.stop_words_zh:
                        keywords.append(w)
                i += 1

        # 去重（保留顺序）
        # 3. 语义归一化（同义词→规范词）
        normalized = []
        for w in dict.fromkeys(keywords):  # 保持顺序去重
            norm_w = self.semantic_norm.get(w, w)  # 映射到规范词
            normalized.append(norm_w)

        # 4. 二次去重（归一化后可能产生新的重复）
        final = []
        for w in normalized:
            if w not in final:
                final.append(w)

        return " ".join(final).strip()

    def _extract_specs(self, text: str) -> Dict[str, str]:
        """提取规格参数（尺寸、颜色、容量等）"""
        specs = {}

        size_patterns = [
            (r"\b(XS|S|M|L|XL|XXL|XXXL)\b", "size"),
            (r"\b(Small|Medium|Large|X-Large)\b", "size"),
            (r"(\d+(?:\.\d+)?)\s*(cm|mm|m|inch|in)\b", "dimension"),
            (r"(\d+(?:\.\d+)?)\s*(ml|l|g|kg|lb|oz)", "capacity"),
        ]

        for pattern, key in size_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                specs[key] = match.group(0).lower()

        # 颜色
        color_match = re.search(
            r"\b(Red|Blue|Green|Yellow|Black|White|Gray|Brown|Pink|Purple)\b", text, re.IGNORECASE
        )
        if color_match:
            specs["color"] = color_match.group(0).lower()

        # 材质
        material_patterns = [
            (
                r"\b(stainless steel|steel|plastic|cotton|fleece|nylon|rubber|silicone|leather|fabric|mesh)\b",
                "material",
            ),
        ]
        for pattern, key in material_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                specs[key] = match.group(0).lower()

        return specs

    def title_similarity(self, title_a: str, title_b: str) -> Tuple[float, Dict]:
        """
        计算标题相似度（多策略加权，针对中英文混合优化）

        权重分配：
        - 50%: 同义词扩展后的 Jaccard 词集相似度
        - 20%: 数字序列匹配（尺寸/容量必须一致）
        - 20%: 规格参数匹配（尺寸/颜色/容量）
        - 10%: 词序相似度（共同词的相对顺序）

        跨语言场景：英文词通过同义词词典转为中文，避免编辑距离惩罚
        """
        if not title_a or not title_b:
            return 0.0, {}

        # 1. 文本标准化（含同义词扩展）
        norm_a = self._normalize_text(title_a)
        norm_b = self._normalize_text(title_b)

        # 2. 词集 Jaccard（核心指标）
        set_a = set(norm_a.split())
        set_b = set(norm_b.split())
        union_len = len(set_a | set_b)
        jaccard = len(set_a & set_b) / union_len if union_len > 0 else 0.0

        # 3. 数字序列匹配
        nums_a = re.findall(r"\d+\.?\d*", title_a)
        nums_b = re.findall(r"\d+\.?\d*", title_b)
        if nums_a and nums_b:
            common = sum(1 for n in nums_a if n in nums_b)
            digit_sim = common / max(len(nums_a), len(nums_b))
        else:
            digit_sim = 1.0 if not nums_a and not nums_b else 0.3

        # 4. 规格参数匹配
        specs_a = self._extract_specs(title_a)
        specs_b = self._extract_specs(title_b)
        spec_sim = 0.0
        if specs_a or specs_b:
            matches = sum(1 for k in specs_a if k in specs_b and specs_a[k] == specs_b[k])
            total = len(set(specs_a.keys()) | set(specs_b.keys()))
            spec_sim = matches / total if total > 0 else 0.0

        # 5. 词序相似度（仅基于共同词）
        common_words = set_a & set_b
        if common_words:
            simple_a = " ".join([w for w in norm_a.split() if w in common_words])
            simple_b = " ".join([w for w in norm_b.split() if w in common_words])
            order_sim = fuzz.ratio(simple_a, simple_b) / 100.0
        else:
            order_sim = 0.0

        # 6. 加权融合
        weights = {"jaccard": 0.50, "digit": 0.20, "spec": 0.20, "order": 0.10}
        final_score = (
            jaccard * weights["jaccard"]
            + digit_sim * weights["digit"]
            + spec_sim * weights["spec"]
            + order_sim * weights["order"]
        )

        # 7. 惩罚项
        if nums_a and nums_b and digit_sim < 0.5:
            final_score *= 0.5

        critical_keys = {"size", "capacity", "dimension"}
        conflicts = sum(
            1 for k in critical_keys if k in specs_a and k in specs_b and specs_a[k] != specs_b[k]
        )
        if conflicts > 0:
            final_score *= 0.7**conflicts

        details = {
            "jaccard": round(jaccard, 3),
            "digit_sim": round(digit_sim, 3),
            "spec_sim": round(spec_sim, 3),
            "order_sim": round(order_sim, 3),
            "final_score": round(final_score, 3),
            "norm_a": norm_a[:80],
            "norm_b": norm_b[:80],
            "common_words": len(common_words),
            "total_words": union_len,
        }

        return final_score, details

    def match(self, amazon_title: str, alibaba_title: str, upc_match: bool = False) -> MatchResult:
        """
        执行匹配（多策略优先级）

        Returns:
            MatchResult
        """
        # 策略1: UPC码匹配（需外部提供）
        if upc_match:
            # TODO: 实现UPC查询逻辑
            pass

        # 策略2: 标题相似度
        score, details = self.title_similarity(amazon_title, alibaba_title)

        # 判定匹配等级（基于优化后的算法）
        if score >= 0.75:
            confidence = "high"
            strategy = "title_fuzzy"
        elif score >= 0.60:
            confidence = "medium"
            strategy = "title_fuzzy"
        else:
            confidence = "low"
            strategy = "title_fuzzy"

        return MatchResult(
            score=score,
            strategy=strategy,
            confidence=confidence,
            details=details,
        )


# ========== 测试入口 ==========

if __name__ == "__main__":
    matcher = FuzzyMatcher()

    test_cases = [
        ("Dog Toy for Aggressive Chewers", "狗狗玩具耐咬大型犬", 0.60),
        (
            "Pet Fountain Water Fountain for Cats and Dogs, 2.4L Stainless Steel",
            "宠物饮水机猫咪狗狗自动饮水器不锈钢活水器 2.4L大容量",
            0.70,
        ),
        ("Cat Litter Box with Lid", "猫咪砂盆带盖封闭式", 0.60),
    ]

    print("=== 宠物用品跨语言匹配测试 ===\n")
    for i, (amz, alib, expected) in enumerate(test_cases, 1):
        result = matcher.match(amz, alib)
        status = "✅" if result.score >= expected else "❌"
        print(f"{status} Case {i}:")
        print(f"  Amazon: {amz[:55]}")
        print(f"  1688:   {alib[:55]}")
        print(f"  得分: {result.score:.1%} (目标 ≥{expected:.0%})")
        print(f"  置信度: {result.confidence}")
        print(f"  归一化A: {result.details['norm_a']}")
        print(f"  归一化B: {result.details['norm_b']}")
        print()
