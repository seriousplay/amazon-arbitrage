"""
Amazon 标题 → 1688 中文搜索词 转换器
提取核心产品词并翻译为中文，提升 1688 搜索精准度
"""

import re

# ─── 英→中产品词库（持续扩展）────────────────────────

TERM_MAP = {
    # 宠物用品
    "dog": "狗", "dogs": "狗", "puppy": "幼犬", "puppies": "幼犬",
    "cat": "猫", "cats": "猫", "kitten": "幼猫", "kittens": "幼猫",
    "pet": "宠物", "pets": "宠物",
    "bird": "鸟", "birds": "鸟",
    "fish": "鱼", "reptile": "爬虫",
    "hamster": "仓鼠", "rabbit": "兔子", "guinea pig": "豚鼠",
    # 产品类型
    "food": "食品", "treat": "零食", "treats": "零食",
    "toy": "玩具", "toys": "玩具",
    "bed": "窝", "beds": "床", "mat": "垫子", "mats": "垫",
    "collar": "项圈", "leash": "牵引绳", "harness": "胸背带",
    "bowl": "碗", "bowls": "碗", "feeder": "喂食器",
    "crate": "笼子", "kennel": "狗笼", "cage": "笼子",
    "carrier": "航空箱", "backpack": "背包",
    "grooming": "美容", "brush": "梳子", "comb": "梳",
    "shampoo": "沐浴露", "conditioner": "护毛素",
    "litter": "猫砂", "litter box": "猫砂盆",
    "scratch": "猫抓板", "scratching post": "猫抓柱",
    "pad": "尿垫", "pads": "尿垫", "diaper": "尿布",
    "training": "训练", "clicker": "响片",
    "chew": "磨牙", "bone": "骨头",
    "clothes": "衣服", "costume": "服装", "sweater": "毛衣",
    "car seat": "车载", "seat cover": "座套",
    "fountain": "饮水机", "water": "饮水",
    "door": "门", "gate": "围栏", "fence": "围栏",
    "stroller": "推车", "wheelchair": "轮椅",
    "health": "保健", "vitamin": "维生素", "supplement": "补剂",
    "medicine": "药品", "pill": "药片",
    "camera": "摄像头", "monitor": "监控",
    "tracker": "追踪器", "gps": "定位器",
    "tag": "吊牌", "id": "身份牌",
    # 材质/特征
    "stainless steel": "不锈钢", "silicone": "硅胶",
    "plastic": "塑料", "wood": "木", "cotton": "棉",
    "leather": "皮革", "nylon": "尼龙", "rubber": "橡胶",
    "plush": "毛绒", "fleece": "摇粒绒",
    "waterproof": "防水", "washable": "可洗",
    "foldable": "折叠", "portable": "便携",
    "automatic": "自动", "interactive": "互动",
    "organic": "有机", "natural": "天然",
    "heavy duty": "重型", "durable": "耐用",
    # 通用
    "bag": "包", "case": "箱", "box": "盒",
    "set": "套装", "kit": "套装",
    "large": "大号", "medium": "中号", "small": "小号",
    "mini": "迷你", "giant": "巨型",
    "black": "黑色", "white": "白色", "blue": "蓝色",
    "red": "红色", "green": "绿色", "pink": "粉色",
    "grey": "灰色", "gray": "灰色", "brown": "棕色",
    # 电子产品
    "phone": "手机", "case": "壳", "charger": "充电器",
    "cable": "数据线", "adapter": "适配器",
    "headphone": "耳机", "earphone": "耳机", "earbuds": "耳机",
    "speaker": "音箱", "bluetooth": "蓝牙",
    "keyboard": "键盘", "mouse": "鼠标",
    "stand": "支架", "holder": "支架", "mount": "支架",
    "light": "灯", "lamp": "灯", "led": "LED",
    "battery": "电池", "power bank": "充电宝",
    "screen protector": "屏幕保护膜",
    # 家居
    "pillow": "枕头", "cushion": "靠垫",
    "blanket": "毯子", "towel": "毛巾",
    "curtain": "窗帘", "rug": "地毯",
    "shelf": "架子", "organizer": "收纳",
    "basket": "篮子", "bin": "收纳箱",
    "bottle": "水杯", "mug": "杯子", "cup": "杯子",
    "knife": "刀", "cutting board": "砧板",
    "pan": "锅", "pot": "锅", "cookware": "炊具",
    # 运动户外
    "tent": "帐篷", "sleeping bag": "睡袋",
    "backpack": "背包", "hiking": "徒步",
    "yoga": "瑜伽", "fitness": "健身",
    "dumbbell": "哑铃", "resistance band": "弹力带",
    "bike": "自行车", "helmet": "头盔",
    # 母婴
    "baby": "婴儿", "diaper": "尿不湿", "stroller": "婴儿车",
    "bib": "围兜", "pacifier": "安抚奶嘴",
    # 办公
    "desk": "桌子", "chair": "椅子",
    "notebook": "笔记本", "pen": "笔",
    "printer": "打印机", "monitor": "显示器",
    # 文具 / 办公
    "glue": "胶水", "stick": "胶棒", "sticks": "胶棒",
    "tape": "胶带", "scissors": "剪刀", "ruler": "尺子",
    "marker": "马克笔", "highlighter": "荧光笔",
    "eraser": "橡皮", "sharpener": "削笔器",
    "binder": "文件夹", "clip": "夹子", "stapler": "订书机",
    "envelope": "信封", "paper": "纸", "notebook": "笔记本",
    "school": "学校", "classroom": "教室",
    "purple": "紫色", "white": "白色", "clear": "透明",
    "washable": "可水洗", "disappearing": "可消失",
    "bulk": "散装", "pack": "套装", "count": "个装",
    # 汽车用品
    "wiper": "雨刮", "wipers": "雨刮器", "blade": "雨刮片", "blades": "雨刮片",
    "windshield": "挡风玻璃", "car": "汽车", "truck": "卡车",
    "automotive": "汽车用品", "vehicle": "车辆",
    "headlight": "大灯", "taillight": "尾灯", "mirror": "后视镜",
    "tire": "轮胎", "wheel": "轮毂", "brake": "刹车", "pad": "刹车片",
    "filter": "滤清器", "oil": "机油", "coolant": "冷却液",
    "mat": "脚垫", "cover": "罩", "seat": "座椅",
    "cleaner": "清洁剂", "wax": "蜡", "polish": "抛光",
    "repellent": "驱水剂", "waterproof": "防水", "coating": "涂层",
    # 家用电器
    "vacuum": "吸尘器", "cleaner": "吸尘器", "mop": "拖把",
    "fan": "风扇", "heater": "取暖器", "humidifier": "加湿器",
    "purifier": "净化器", "filter": "滤芯", "air": "空气",
    "coffee": "咖啡", "maker": "机", "blender": "搅拌机",
    "toaster": "烤面包机", "microwave": "微波炉", "oven": "烤箱",
    "refrigerator": "冰箱", "freezer": "冰柜", "washer": "洗衣机",
    "dryer": "烘干机", "dishwasher": "洗碗机",
    # 美容化妆
    "ointment": "软膏", "cream": "霜", "lotion": "乳液",
    "serum": "精华", "sunscreen": "防晒", "moisturizer": "保湿",
    "cleanser": "洁面", "toner": "爽肤水", "mask": "面膜",
    "lip": "唇", "eye": "眼", "face": "脸", "body": "身体",
    "makeup": "化妆品", "powder": "粉", "brush": "刷",
    "nail": "指甲", "polish": "指甲油", "gel": "凝胶",
    "hair": "头发", "shampoo": "洗发水", "conditioner": "护发素",
    "dryer": "吹风机", "straightener": "直发器", "curler": "卷发器",
    "razor": "剃须刀", "shaver": "剃须刀", "trimmer": "修剪器",
    "perfume": "香水", "deodorant": "止汗露",
    # 婴幼儿
    "diaper": "尿布", "wipes": "湿巾", "rash": "疹",
    "healing": "修护", "protectant": "保护", "skin": "皮肤",
    "baby": "婴儿", "infant": "婴幼儿", "toddler": "幼儿",
    "bottle": "奶瓶", "pacifier": "安抚奶嘴", "bib": "围兜",
    "stroller": "童车", "crib": "婴儿床", "carrier": "婴儿背带",
    "formula": "奶粉", "puree": "辅食泥",
    # 雨刮相关
    "rain": "雨", "all weather": "全天候", "streak": "条纹",
    "visibility": "能见度", "formula": "配方", "exclusive": "独家",
    "pack of": "套装", "inches": "英寸", "inch": "英寸",
    # 品牌名映射（用于辅助搜索）
    "aquaphor": "优色林", "rainx": "RainX", "rain-x": "RainX",
    "elmer": "Elmer", "elmers": "Elmer's",
    # 复合词（必须整体匹配才有意义）
    "instant film": "拍立得相纸", "instax mini": "instax mini 相纸",
    "instant camera": "拍立得相机", "polaroid": "拍立得",
    "twin pack": "双包装", "value pack": "超值装",
    "gift set": "礼盒装", "starter kit": "入门套装",
    "replacement": "替换装", "refill": "补充装",
    "disposable": "一次性", "reusable": "可重复使用",
    "stainless steel": "不锈钢", "cast iron": "铸铁",
    "tempered glass": "钢化玻璃", "bamboo": "竹制",
    "memory foam": "记忆棉", "gel memory foam": "凝胶记忆棉",
    "wireless charger": "无线充电器", "fast charging": "快充",
    "power strip": "插排", "extension cord": "延长线",
    "usb hub": "USB集线器", "card reader": "读卡器",
    "webcam": "摄像头", "ring light": "补光灯",
    "tripod": "三脚架", "selfie stick": "自拍杆",
    "screen protector": "手机膜", "phone case": "手机壳",
    "air fryer": "空气炸锅", "rice cooker": "电饭煲",
    "pressure cooker": "压力锅", "slow cooker": "慢炖锅",
    "food processor": "料理机", "coffee maker": "咖啡机",
    "electric kettle": "电水壶", "toaster oven": "烤面包机",
    "water bottle": "水杯", "lunch box": "饭盒",
    "food container": "食品盒", "storage bin": "收纳箱",
    "laundry basket": "洗衣篮", "trash can": "垃圾桶",
    "shower curtain": "浴帘", "bath mat": "浴室垫",
    "bed sheet": "床单", "comforter": "被子", "duvet": "羽绒被",
    "throw pillow": "抱枕", "area rug": "地毯",
    "led strip": "LED灯带", "fairy lights": "装饰灯串",
    "solar light": "太阳能灯", "motion sensor": "感应器",
    "security camera": "监控摄像头", "doorbell": "门铃",
    "smart plug": "智能插座", "smart bulb": "智能灯泡",
    "yoga mat": "瑜伽垫", "resistance band": "弹力带",
    "jump rope": "跳绳", "exercise bike": "健身车",
    "dumbbell": "哑铃", "dumbbells": "哑铃", "weight": "负重",
    "weights": "负重", "hand weight": "哑铃", "hand weights": "哑铃",
    "dumbbell set": "哑铃套装", "kettlebell": "壶铃",
    "neoprene": "氯丁橡胶", "exercise": "健身", "muscle": "肌肉",
    "toning": "塑形", "workout": "训练", "strength": "力量",
    "barbell": "杠铃", "weight plate": "杠铃片",
    "weight bench": "健身凳", "pull up": "引体向上",
    "push up": "俯卧撑", "sit up": "仰卧起坐",
    "gym": "健身房", "fitness": "健身", "cardio": "有氧",
    "treadmill": "跑步机", "elliptical": "椭圆机",
    "rowing machine": "划船机", "spin bike": "动感单车",
    "protein powder": "蛋白粉", "massage gun": "筋膜枪",
    "foam roller": "泡沫轴", "exercise ball": "健身球",
    "tent camping": "帐篷", "sleeping bag": "睡袋",
    "hiking backpack": "登山包", "fishing rod": "鱼竿",
    "cooler bag": "保温袋", "picnic blanket": "野餐垫",
    "car seat": "安全座椅", "baby carrier": "婴儿背带",
    "diaper bag": "妈咪包", "baby monitor": "婴儿监护器",
    "breast pump": "吸奶器", "bottle warmer": "暖奶器",
    "changing pad": "尿布垫", "play mat": "爬行垫",
    "dog food": "狗粮", "cat food": "猫粮",
    "pet bed": "宠物窝", "cat tree": "猫爬架",
    "litter box": "猫砂盆", "dog leash": "狗绳",
    "cat toy": "猫玩具", "dog toy": "狗玩具",
    "pet carrier": "宠物背包", "poop bags": "拾便袋",
    "fujifilm": "富士", "instax": "instax", "fuji": "富士",
    "canon": "佳能", "nikon": "尼康", "sony": "索尼",
    "samsung": "三星", "apple": "苹果", "xiaomi": "小米",
    "huawei": "华为", "bose": "Bose", "jbl": "JBL",
    "dyson": "戴森", "irobot": "iRobot", "roomba": "Roomba",
    "nintendo": "任天堂", "playstation": "PS", "xbox": "Xbox",
    "lego": "乐高", "barbie": "芭比", "nerf": "Nerf",
    "crayola": "Crayola", "sharpie": "Sharpie",
    "stanley": "Stanley", "yeti": "YETI", "hydro": "Hydro",
    "kleenex": "舒洁", "clorox": "高乐氏", "lysol": "来苏尔",
    "tide": "汰渍", "dawn": "Dawn", "cascade": "Cascade",
    "oral": "欧乐B", "crest": "佳洁士", "colgate": "高露洁",
    "gillette": "吉列", "dove": "多芬", "nivea": "妮维雅",
    "vaseline": "凡士林", "cetaphil": "丝塔芙", "neutrogena": "露得清",
    "loreal": "欧莱雅", "maybelline": "美宝莲", "revlon": "露华浓",
}

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
    "the", "a", "an", "and", "or", "for", "of", "in", "on", "to",
    "with", "by", "is", "are", "was", "were", "be", "been",
    "it", "its", "that", "this", "these", "those",
    "pack", "count", "ounce", "oz", "lb", "lbs", "pound",
    "inch", "inches", "cm", "mm", "size", "color",
    "new", "best", "top", "premium", "original",
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
        return " ".join(en_fallback) if en_fallback else title.split()[:3]

    return " ".join(result[:6])


def translate_detail(title: str) -> dict:
    """返回翻译详情（原始 → 关键词 → 中文搜索词）"""
    return {
        "original": title,
        "keywords": extract_keywords(title),
        "chinese": to_chinese(title),
    }
