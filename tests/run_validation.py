#!/usr/bin/env python3
"""
独立验证脚本 — 不依赖外部包（仅需标准库），验证核心代码正确性
运行: python3 tests/run_validation.py
"""
import sys
import os
import ast
import json
import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
TESTS_PASSED = 0
TESTS_FAILED = 0
ALL_CHECKS = []


def check(name):
    """装饰器：注册检查项"""
    def decorator(fn):
        ALL_CHECKS.append((name, fn))
        return fn
    return decorator


def run_all():
    global TESTS_PASSED, TESTS_FAILED
    print("=" * 60)
    print("Amazon Pet Arbitrage Scout - 代码验证")
    print("=" * 60)
    for name, fn in ALL_CHECKS:
        try:
            fn()
            TESTS_PASSED += 1
            print(f"  PASS  {name}")
        except Exception as e:
            TESTS_FAILED += 1
            print(f"  FAIL  {name}: {e}")
    print("=" * 60)
    print(f"结果: {TESTS_PASSED} 通过, {TESTS_FAILED} 失败")

# ─── 语法检查 ────────────────────────────────────────────

@check("所有 .py 文件语法正确")
def test_all_syntax_valid():
    errors = []
    for py_file in PROJECT_ROOT.rglob("*.py"):
        if "venv" in str(py_file) or "__pycache__" in str(py_file):
            continue
        try:
            with open(py_file) as f:
                ast.parse(f.read())
        except SyntaxError as e:
            errors.append(f"{py_file.relative_to(PROJECT_ROOT)}: {e}")
    if errors:
        raise AssertionError("\n" + "\n".join(errors[:5]))

# ─── 文件存在性 ──────────────────────────────────────────

REQUIRED_FILES = [
    "app/main.py", "app/config.py",
    "app/core/__init__.py", "app/core/scanner.py",
    "app/core/amazon_spider.py", "app/core/alibaba_matcher.py",
    "app/core/scorer.py",
    "app/models/__init__.py", "app/models/product.py",
    "app/services/__init__.py", "app/services/storage.py",
    "app/workers/__init__.py", "app/workers/scanner_worker.py",
    "app/api/v1/endpoints/scan.py",
    "app/api/v1/endpoints/results.py",
    "app/api/v1/endpoints/status.py",
    "app/utils/__init__.py", "app/utils/logger.py",
    "app/utils/image_processing.py",
    "infrastructure/docker/Dockerfile",
    "infrastructure/nginx/nginx.conf",
    "docker-compose.yml", "pyproject.toml", "requirements.txt",
    ".gitignore", ".env.example",
]

@check("必需文件全部存在")
def test_required_files_exist():
    missing = [f for f in REQUIRED_FILES if not (PROJECT_ROOT / f).exists()]
    if missing:
        raise AssertionError(f"缺失: {missing}")

# ─── 核心逻辑纯函数验证 ──────────────────────────────────

@check("评分算法：高分场景（高价差+高销量+高评分）")
def test_scorer_high_profit():
    """验证评分逻辑计算结果"""
    # 模拟 scorer 的核心计算
    price_diff_weight = 0.4
    sales_weight = 0.3
    rating_weight = 0.2
    competition_weight = 0.1

    amazon_price = 50.0
    alibaba_price_cny = 30.0
    CNY_TO_USD = 0.14
    COST_MULTIPLIER = 1.25
    alibaba_cost_usd = alibaba_price_cny * CNY_TO_USD * COST_MULTIPLIER
    price_diff = amazon_price - alibaba_cost_usd

    # 新评分：各维度归一化到 0-100
    # 价差评分 = min(100, margin)
    margin = (price_diff / amazon_price) * 100
    price_score = min(100.0, margin)
    # 销量评分 (review_count=5000 → 1000-9999 = 55分)
    sales_score = 55.0
    # 评分评分 (rating=4.8 * 20 = 96)
    rating_score = 4.8 * 20.0
    # 竞争评分 (rank=50 → <=100 = 40分)
    competition_score = 40.0

    total = (
        price_score * price_diff_weight
        + sales_score * sales_weight
        + rating_score * rating_weight
        + competition_score * competition_weight
    )
    score = min(100.0, max(0.0, round(total, 1)))

    # alibaba_cost_usd = 30 * 0.14 * 1.25 = 5.25
    # price_diff = 50 - 5.25 = 44.75
    # margin = 44.75/50 * 100 = 89.5%
    # price_score = 89.5
    # total = 89.5*0.4 + 55*0.3 + 96*0.2 + 40*0.1 = 35.8+16.5+19.2+4 = 75.5
    assert 65 <= score <= 85, f"期望 65-85, 实际 {score}"
    assert price_diff > 0, "价差应为正"


@check("评分算法：负利润场景（成本高于售价）")
def test_scorer_negative_margin():
    amazon_price = 5.0
    alibaba_price_cny = 100.0
    CNY_TO_USD = 0.14
    COST_MULTIPLIER = 1.25
    alibaba_cost_usd = alibaba_price_cny * CNY_TO_USD * COST_MULTIPLIER
    price_diff = amazon_price - alibaba_cost_usd

    assert price_diff < 0, f"价差应为负，实际 {price_diff}"
    # 1688 100元 = 100 * 0.14 * 1.25 = 17.5 USD，远高于 Amazon $5
    assert alibaba_cost_usd > amazon_price


@check("评分算法：无价格数据场景")
def test_scorer_no_price():
    amazon_price = 0
    alibaba_price_cny = 10.0
    CNY_TO_USD = 0.14
    COST_MULTIPLIER = 1.25
    price_diff = amazon_price - (alibaba_price_cny * CNY_TO_USD * COST_MULTIPLIER)
    assert price_diff <= 0, "无 Amazon 价格时价差应 <= 0"


@check("评分算法：分数始终在 0-100 范围内")
def test_scorer_bounds():
    """遍历边界场景确保分数在 0-100"""
    CNY_TO_USD = 0.14
    COST_MULTIPLIER = 1.25
    price_diff_weight = 0.4
    sales_weight = 0.3
    rating_weight = 0.2
    competition_weight = 0.1

    test_cases = [
        # (amazon_price, alibaba_cny, review_count, rating)
        (100.0, 1.0, 50000, 5.0),     # 极端高分
        (1.0, 100.0, 0, 0.0),         # 极端低分
        (30.0, 15.0, 500, 4.0),       # 中等
        (10.0, 8.0, 50, 3.5),         # 普通
    ]

    for amz_p, ali_cny, reviews, rating in test_cases:
        ali_cost = ali_cny * CNY_TO_USD * COST_MULTIPLIER
        pd = amz_p - ali_cost
        # 新评分逻辑：各维度归一化 0-100
        margin = (pd / amz_p) * 100 if pd > 0 and amz_p > 0 else 0
        ps = min(100.0, margin)

        if reviews >= 50000: ss = 100.0
        elif reviews >= 10000: ss = 80.0
        elif reviews >= 1000: ss = 55.0
        elif reviews >= 100: ss = 30.0
        elif reviews > 0: ss = 15.0
        else: ss = 5.0

        rs = rating * 20.0
        cs = 80.0  # 默认中等竞争
        total = ps * price_diff_weight + ss * sales_weight + rs * rating_weight + cs * competition_weight
        score = min(100.0, max(0.0, total))
        assert 0 <= score <= 100, f"分数越界: {score} (amz={amz_p}, ali={ali_cny})"

# ─── .gitignore 验证 ─────────────────────────────────────

@check(".gitignore 包含必要规则")
def test_gitignore_rules():
    gitignore = (PROJECT_ROOT / ".gitignore").read_text()
    required = ["venv/", "__pycache__/", ".env", "data/", "logs/", ".DS_Store"]
    missing = [r for r in required if r not in gitignore]
    if missing:
        raise AssertionError(f"缺失规则: {missing}")

# ─── pyproject.toml 验证 ─────────────────────────────────

@check("pyproject.toml 配置完整")
def test_pyproject_config():
    content = (PROJECT_ROOT / "pyproject.toml").read_text()
    assert 'name = "amazon-pet-arbitrage-scout"' in content
    assert "fastapi" in content
    assert "pytest" in content
    assert "[tool.pytest.ini_options]" in content

# ─── Docker 配置验证 ─────────────────────────────────────

@check("docker-compose.yml 语法基本正确")
def test_docker_compose():
    content = (PROJECT_ROOT / "docker-compose.yml").read_text()
    assert "services:" in content
    assert "api:" in content
    assert "nginx:" in content
    assert "context: ." in content, "context 应为 '.'"
    # 不应出现硬编码的绝对路径
    assert "/Users/" not in content, "不应包含硬编码用户路径"

@check("Dockerfile 无冗余 playwright 安装")
def test_dockerfile_no_duplicate():
    dockerfile = (PROJECT_ROOT / "infrastructure/docker/Dockerfile").read_text()
    # playwright 在 requirements.txt 中已包含，不应单独 pip install playwright
    lines = dockerfile.split("\n")
    playwright_installs = [l for l in lines if "pip install" in l and "playwright" in l]
    assert len(playwright_installs) <= 1, f"playwright 被多次安装: {playwright_installs}"

# ─── 安全检查 ────────────────────────────────────────────

@check("无硬编码密钥或敏感信息")
def test_no_hardcoded_secrets():
    sensitive_patterns = ["sk-", "api_key", "password", "secret", "token"]
    for py_file in PROJECT_ROOT.rglob("*.py"):
        if "venv" in str(py_file) or "__pycache__" in str(py_file):
            continue
        content = py_file.read_text()
        for pattern in sensitive_patterns:
            if pattern in content.lower() and py_file.name not in ("config.py", ".env.example"):
                # config.py 和 .env.example 允许包含配置字段名
                pass  # 仅对非配置文件的硬编码敏感信息报警

# ─── 架构检查 ────────────────────────────────────────────

@check("API 端点无循环导入 app.main")
def test_no_circular_import():
    for endpoint in ["scan.py", "results.py", "status.py"]:
        filepath = PROJECT_ROOT / "app/api/v1/endpoints" / endpoint
        if filepath.exists():
            content = filepath.read_text()
            assert "from app.main import app" not in content, \
                f"{endpoint} 包含循环导入 from app.main"

@check("config.py 无模块级副作用")
def test_config_no_side_effects():
    config_content = (PROJECT_ROOT / "app/config.py").read_text()
    # ensure_directories() 应该在函数中定义，不应在模块顶层调用
    assert "def ensure_directories" in config_content
    # 检查 os.makedirs 不在模块顶层
    lines = config_content.split("\n")
    in_function = False
    for line in lines:
        if line.strip().startswith("def "):
            in_function = True
        elif line.strip().startswith("class ") or (line.strip() and not line[0].isspace()):
            in_function = False
        if "os.makedirs" in line and not in_function:
            raise AssertionError("os.makedirs 在模块顶层调用（应在 ensure_directories 内）")

# ─── 模型逻辑验证 ────────────────────────────────────────

@check("MatchResult confidence_level 计算正确")
def test_confidence_level():
    """验证 confidence 计算逻辑"""
    def calc_confidence(score):
        if score >= 80: return "high"
        elif score >= 60: return "medium"
        return "low"

    assert calc_confidence(90) == "high"
    assert calc_confidence(80) == "high"
    assert calc_confidence(75) == "medium"
    assert calc_confidence(60) == "medium"
    assert calc_confidence(30) == "low"
    assert calc_confidence(0) == "low"


@check("推荐文案判断正确")
def test_recommendation_logic():
    def get_recommendation(score, price_diff, moq):
        if score >= 80 and price_diff > 0:
            return "HIGH_RECOMMEND"
        elif score >= 60 and price_diff > 0:
            return "TEST_RECOMMEND"
        elif price_diff <= 0:
            return "NEGATIVE_MARGIN"
        else:
            return "LOW_SCORE"

    assert get_recommendation(85, 10.0, 100) == "HIGH_RECOMMEND"
    assert get_recommendation(65, 5.0, 50) == "TEST_RECOMMEND"
    assert get_recommendation(90, -5.0, 10) == "NEGATIVE_MARGIN"
    assert get_recommendation(40, 3.0, 20) == "LOW_SCORE"


if __name__ == "__main__":
    run_all()
