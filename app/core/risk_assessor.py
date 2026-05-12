"""
风险评估器 — 侵权/季节/认证/物流风险
基于 PDF 选品逻辑中的第4、8、9、10条规则
"""

import re
from typing import Dict, List, Optional

from app.models.product import AmazonProduct

# ─── 已知注册商标品牌（高风险，不可碰）─────────────────
TRADEMARKED_BRANDS = {
    "nike",
    "adidas",
    "gucci",
    "louis vuitton",
    "chanel",
    "hermes",
    "disney",
    "marvel",
    "star wars",
    "harry potter",
    "pokemon",
    "nintendo",
    "playstation",
    "xbox",
    "apple",
    "samsung",
    "lego",
    "barbie",
    "hot wheels",
    "frozen",
    "paw patrol",
    "coco melon",
    "peppa pig",
    "spiderman",
    "batman",
    "superman",
    "hello kitty",
    "minions",
    "transformers",
    "nerf",
    "fisher price",
    "vtech",
    "leapfrog",
    "melissa doug",
    "crayola",
    "play doh",
    "bose",
    "sony",
    "jbl",
    "beats",
    "dyson",
    "irobot",
    "keurig",
    "nespresso",
    "kitchenaid",
    "instant pot",
    "swiffer",
    "febreze",
    "mr clean",
    "magic eraser",
    "yeti",
    "stanley",
    "hydro flask",
    "owala",
    "lululemon",
    "under armour",
    "the north face",
    "patagonia",
    "coach",
    "michael kors",
    "kate spade",
    "tory burch",
    "ray ban",
    "oakley",
    "warby parker",
    "ugg",
    "crocs",
    "birkenstock",
    "dr martens",
    "victoria secret",
    "calvin klein",
    "tommy hilfiger",
    "ralph lauren",
    "lacoste",
    "burberry",
}

# ─── 需要强制认证的品类 ────────────────────────────────
RESTRICTED_CATEGORIES = {
    "medical": "需要 FDA 认证",
    "pharmacy": "需要 FDA 认证",
    "health": "可能需要 FDA 认证",
    "supplements": "需要 FDA 认证",
    "drug": "需要 FDA 认证",
    "baby food": "需要 FDA 认证",
    "infant": "需要 CPSC 认证",
    "children": "需要 CPSC 认证",
    "toy": "需要 CPSC/ASTM 认证",
    "electronic": "需要 FCC 认证",
    "battery": "需要 UN38.3 认证",
    "laser": "需要 FDA 认证",
    "cosmetic": "需要 FDA 注册",
    "contact lens": "需要 FDA 认证",
    "pet food": "需要 FDA 认证",
    "pesticide": "需要 EPA 认证",
    "firearm": "禁止销售",
    "weapon": "可能需要许可",
    "alcohol": "需要许可证",
    "tobacco": "禁止销售",
}

# ─── 季节性关键词 ─────────────────────────────────────
SEASONAL_PATTERNS = {
    "christmas": ("圣诞季", 11, 12),
    "halloween": ("万圣节", 9, 10),
    "thanksgiving": ("感恩节", 11, 11),
    "valentine": ("情人节", 1, 2),
    "easter": ("复活节", 3, 4),
    "back to school": ("返校季", 7, 9),
    "summer": ("夏季", 6, 8),
    "winter": ("冬季", 11, 2),
    "spring": ("春季", 3, 5),
    "fall": ("秋季", 9, 11),
    "graduation": ("毕业季", 5, 6),
    "wedding": ("婚礼季", 5, 9),
    "prime day": ("Prime Day", 7, 7),
    "black friday": ("黑五", 11, 11),
    "cyber monday": ("网一", 11, 11),
}

# ─── 高风险品类（退货率高/易碎/大件）─────────────────
HIGH_RISK_INDICATORS = {
    "glass": ("易碎品", -2),
    "ceramic": ("易碎品", -2),
    "fragile": ("易碎品", -2),
    "liquid": ("液体物流限制", -1),
    "electronic": ("退货率高", -1),
    "clothing": ("尺码退货", -1),
    "shoes": ("尺码退货", -1),
    "furniture": ("大件物流贵", -2),
    "heavy": ("重量超标", -1),
    "large": ("体积超标", -1),
    "bulky": ("体积超标", -1),
    "perishable": ("易腐坏", -3),
    "flammable": ("危险品", -5),
    "battery": ("危险品", -2),
    "magnet": ("物流限制", -1),
}


class RiskAssessor:
    """风险评估器"""

    def assess(self, product: AmazonProduct) -> dict:
        """综合风险评估"""
        risks = []
        score = 10  # 满分 10，逐项扣分

        # 1. 商标侵权检测
        title_lower = product.title.lower()
        for brand in TRADEMARKED_BRANDS:
            if brand in title_lower:
                risks.append(f"⚠️ 含注册商标 '{brand}'，侵权风险极高")
                score -= 5
                break

        # 2. 品类认证检测
        if product.category_path:
            cat_lower = product.category_path.lower()
            for keyword, cert in RESTRICTED_CATEGORIES.items():
                if keyword in cat_lower:
                    risks.append(f"📋 {cert}")
                    if "禁止" in cert:
                        score -= 5
                    else:
                        score -= 1
                    break

        # 3. 季节性检测
        for keyword, (name, start, end) in SEASONAL_PATTERNS.items():
            if keyword in title_lower:
                risks.append(f"📅 季节性产品 ({name})，注意备货窗口")
                score -= 1
                break

        # 4. 物流/退货风险
        full_text = (product.title + " " + (product.category_path or "")).lower()
        for keyword, (desc, penalty) in HIGH_RISK_INDICATORS.items():
            if keyword in full_text:
                risks.append(f"📦 {desc}")
                score += penalty  # penalty 是负数
                break

        # 5. 评分过低 → 质量风险
        if product.rating and product.rating < 3.8:
            risks.append("📉 评分偏低，可能存在质量缺陷")
            score -= 1

        score = max(0, min(10, score))

        return {
            "score": score,
            "level": "低风险" if score >= 8 else "中风险" if score >= 5 else "高风险",
            "risks": risks[:5],
            "certification_needed": any("认证" in r or "许可" in r for r in risks),
            "seasonal": any("季节性" in r for r in risks),
            "trademark_risk": any("侵权" in r for r in risks),
        }
