"""
Amazon 类目路径 → 1688 精准搜索词 映射
基于 Amazon 自有类目体系，远比关键词翻译可靠
"""

# Amazon 叶子类目 → 1688 搜索词
# 格式: "类目名" → "中文搜索词"
CATEGORY_MAP = {
    # 宠物
    "pet supplies": "宠物用品", "pet": "宠物用品",
    "dogs": "狗用品", "dog food": "狗粮", "dog treats": "狗零食",
    "dog toys": "狗玩具", "dog beds": "狗窝", "dog collars": "狗项圈",
    "dog leashes": "狗牵引绳", "dog grooming": "狗美容",
    "cats": "猫用品", "cat food": "猫粮", "cat treats": "猫零食",
    "cat toys": "猫玩具", "cat litter": "猫砂", "cat beds": "猫窝",
    "litter boxes": "猫砂盆", "cat scratching posts": "猫抓板",
    "birds": "鸟用品", "bird food": "鸟食", "bird cages": "鸟笼",
    "fish": "鱼用品", "aquariums": "鱼缸", "fish food": "鱼食",
    "small animals": "小宠", "hamsters": "仓鼠用品",
    "reptiles": "爬虫用品",

    # 运动健身
    "dumbbells": "哑铃", "hand weights": "哑铃", "free weights": "哑铃",
    "weight sets": "哑铃套装", "kettlebells": "壶铃",
    "exercise & fitness": "健身器材", "strength training": "力量训练",
    "resistance bands": "弹力带", "yoga mats": "瑜伽垫",
    "yoga": "瑜伽", "yoga blocks": "瑜伽砖", "yoga straps": "瑜伽带",
    "exercise balls": "健身球", "foam rollers": "泡沫轴",
    "jump ropes": "跳绳", "treadmills": "跑步机",
    "elliptical machines": "椭圆机", "exercise bikes": "健身车",
    "weight benches": "健身凳", "pull up bars": "引体向上杆",
    "push up": "俯卧撑", "abdominal": "腹肌", "core training": "核心训练",
    "sports": "运动", "outdoor recreation": "户外",

    # 电子产品
    "headphones": "耳机", "earbuds": "蓝牙耳机", "earphones": "耳机",
    "wireless earbuds": "无线耳机", "bluetooth earbuds": "蓝牙耳机",
    "speakers": "音箱", "bluetooth speakers": "蓝牙音箱",
    "portable speakers": "便携音箱", "chargers": "充电器",
    "usb chargers": "USB充电器", "wireless chargers": "无线充电器",
    "charging cables": "数据线", "usb cables": "数据线",
    "power banks": "充电宝", "portable power": "充电宝",
    "phone cases": "手机壳", "screen protectors": "手机膜",
    "smartphone": "手机配件", "cell phone": "手机配件",
    "tablets": "平板配件", "ipad": "iPad配件",
    "laptops": "笔记本配件", "laptop": "笔记本配件",
    "keyboards": "键盘", "mice": "鼠标", "mouse": "鼠标",
    "webcams": "摄像头", "monitors": "显示器",
    "computer accessories": "电脑配件", "camera": "相机配件",
    "video games": "游戏配件", "gaming": "游戏",

    # 家居厨房
    "kitchen & dining": "厨房用品", "kitchen": "厨房用品",
    "cookware": "炊具", "pots & pans": "锅具",
    "cutlery": "餐具", "knives": "刀具", "cutting boards": "砧板",
    "kitchen gadgets": "厨房工具", "utensils": "厨具",
    "food storage": "食品收纳", "containers": "收纳盒",
    "water bottles": "水杯", "tumblers": "水杯", "mugs": "杯子",
    "coffee makers": "咖啡机", "espresso": "咖啡机",
    "coffee": "咖啡", "tea": "茶",
    "blenders": "搅拌机", "food processors": "料理机",
    "toasters": "烤面包机", "air fryers": "空气炸锅",
    "rice cookers": "电饭煲", "pressure cookers": "压力锅",
    "slow cookers": "慢炖锅", "electric kettles": "电水壶",
    "vacuum": "吸尘器", "floor care": "清洁电器",
    "home": "家居", "storage": "收纳", "organization": "收纳",
    "bedding": "床上用品", "sheets": "床单", "pillows": "枕头",
    "towels": "毛巾", "bath": "浴室", "shower": "淋浴",
    "curtains": "窗帘", "rugs": "地毯", "lighting": "灯具",
    "furniture": "家具", "desk": "桌子", "chair": "椅子",

    # 美容
    "beauty": "美容", "skincare": "护肤", "skin care": "护肤",
    "moisturizers": "保湿霜", "face creams": "面霜",
    "serums": "精华", "sunscreen": "防晒霜",
    "cleansers": "洗面奶", "toners": "爽肤水", "masks": "面膜",
    "makeup": "化妆品", "lipstick": "口红", "eyeshadow": "眼影",
    "foundation": "粉底", "mascara": "睫毛膏",
    "hair care": "护发", "shampoo": "洗发水", "conditioner": "护发素",
    "hair dryers": "吹风机", "hair styling": "美发工具",
    "nail care": "美甲", "nail polish": "指甲油",
    "bath & body": "沐浴", "body lotion": "身体乳",
    "deodorant": "止汗露", "perfume": "香水",
    "shaving": "剃须", "razors": "剃须刀", "trimmers": "修剪器",
    "oral care": "口腔护理", "toothbrush": "牙刷",
    "toothpaste": "牙膏", "electric toothbrush": "电动牙刷",

    # 婴儿
    "baby": "婴儿用品", "diapers": "纸尿裤", "baby wipes": "婴儿湿巾",
    "baby food": "婴儿食品", "formula": "奶粉",
    "baby bottles": "奶瓶", "pacifiers": "安抚奶嘴",
    "baby clothes": "婴儿服装", "onesies": "连体衣",
    "strollers": "婴儿推车", "car seats": "安全座椅",
    "baby carriers": "婴儿背带", "baby monitors": "婴儿监护器",
    "nursing": "哺乳用品", "breast pumps": "吸奶器",
    "baby toys": "婴儿玩具", "teething": "牙胶",
    "cribs": "婴儿床", "changing pads": "尿布垫",
    "diaper bags": "妈咪包", "play mats": "爬行垫",

    # 办公文具
    "office": "办公", "office supplies": "办公文具",
    "paper": "纸", "notebooks": "笔记本", "journals": "日记本",
    "pens": "笔", "pencils": "铅笔", "markers": "马克笔",
    "highlighters": "荧光笔", "erasers": "橡皮",
    "tape": "胶带", "glue": "胶水", "scissors": "剪刀",
    "staplers": "订书机", "binders": "文件夹", "clips": "夹子",
    "envelopes": "信封", "labels": "标签",
    "desk accessories": "桌面收纳", "desk organizers": "桌面收纳",
    "calculators": "计算器", "office electronics": "办公电子",

    # 工具家装
    "tools": "工具", "power tools": "电动工具", "hand tools": "手工工具",
    "drills": "电钻", "screwdrivers": "螺丝刀", "wrenches": "扳手",
    "hammers": "锤子", "saws": "锯子", "pliers": "钳子",
    "measuring": "测量工具", "tape measure": "卷尺",
    "hardware": "五金", "fasteners": "紧固件", "screws": "螺丝",
    "painting": "油漆", "paint": "涂料", "brushes": "刷子",
    "safety": "安全", "gloves": "手套", "goggles": "护目镜",
    "home improvement": "家装", "lighting": "灯", "led": "LED",

    # 汽车
    "automotive": "汽车用品", "car care": "汽车美容",
    "car accessories": "汽车配件", "interior": "汽车内饰",
    "exterior": "汽车外饰", "wiper blades": "雨刮器",
    "windshield wipers": "雨刮器", "windshield": "挡风玻璃",
    "car mats": "汽车脚垫", "seat covers": "汽车座套",
    "car cleaning": "汽车清洁", "car wax": "车蜡",
    "motor oil": "机油", "filters": "滤清器",
    "tires": "轮胎", "car electronics": "汽车电子",
    "phone mounts": "手机支架", "car chargers": "车载充电器",


    # 服装
    "clothing": "服装", "shoes": "鞋", "jewelry": "首饰",
    "men": "男装", "women": "女装", "kids": "童装",
    "t-shirts": "T恤", "shirts": "衬衫", "pants": "裤子",
    "dresses": "连衣裙", "jackets": "外套", "sweaters": "毛衣",
    "socks": "袜子", "underwear": "内衣",
    "sneakers": "运动鞋", "boots": "靴子", "sandals": "凉鞋",
    "watches": "手表", "necklaces": "项链", "earrings": "耳环",
    "rings": "戒指", "bracelets": "手链",

    # 玩具
    "toys": "玩具", "games": "游戏",
    "action figures": "人偶", "dolls": "娃娃",
    "building toys": "积木", "blocks": "积木", "lego": "乐高",
    "puzzles": "拼图", "board games": "桌游",
    "arts & crafts": "手工", "crafts": "手工", "art": "美术",
    "coloring": "涂色", "painting": "绘画", "drawing": "画画",
    "outdoor play": "户外玩具", "sports toys": "运动玩具",
    "educational": "教育玩具", "stem toys": "STEM玩具",
    "rc toys": "遥控玩具", "drones": "无人机",
    "stuffed animals": "毛绒玩具", "plush": "毛绒",

    # 图书
    "books": "图书", "kindle": "电子书",
    "fiction": "小说", "nonfiction": "非虚构",
    "childrens books": "儿童图书", "picture books": "绘本",
    "textbooks": "教材", "education": "教育",
    "cookbooks": "食谱", "self-help": "自助",

    # 食品
    "grocery": "食品", "gourmet food": "美食",
    "snacks": "零食", "chips": "薯片", "cookies": "饼干",
    "candy": "糖果", "chocolate": "巧克力",
    "coffee": "咖啡", "tea": "茶",
    "cereal": "麦片", "pasta": "意面", "rice": "大米",
    "canned": "罐头", "condiments": "调味品", "sauces": "酱料",
    "beverages": "饮料", "water": "水", "juice": "果汁",
    "protein": "蛋白粉", "supplements": "补剂",
    "vitamins": "维生素", "snack bars": "能量棒",

    # 工业
    "industrial": "工业用品", "scientific": "科学仪器",
    "lab": "实验室", "safety": "安全防护",
    "janitorial": "清洁用品", "cleaning": "清洁",
    "material handling": "物料搬运", "packaging": "包装",
    "electrical": "电气", "wiring": "电线",
    "plumbing": "管道", "hvac": "暖通",

    # 乐器
    "musical instruments": "乐器", "guitars": "吉他",
    "keyboards": "电子琴", "pianos": "钢琴",
    "drums": "鼓", "percussion": "打击乐器",
    "wind instruments": "管乐器", "strings": "弦乐器",
    "accessories": "配件", "music": "音乐",

    # 花园
    "garden": "花园", "outdoor": "户外",
    "plants": "植物", "seeds": "种子", "gardening tools": "园艺工具",
    "patio": "露台", "lawn": "草坪", "grills": "烧烤架",
    "outdoor furniture": "户外家具", "camping": "露营",
    "tents": "帐篷", "sleeping bags": "睡袋",
    "hiking": "徒步", "fishing": "钓鱼",
    "hunting": "狩猎", "tactical": "战术装备",
    "bikes": "自行车", "cycling": "骑行",
}


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
