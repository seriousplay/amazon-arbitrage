#!/bin/bash
# Amazon Pet Arbitrage Scout - 本地启动脚本

set -e

echo "=========================================="
echo "🐾 Amazon Pet Arbitrage Scout"
echo "=========================================="
echo ""

# 检查 Python 版本
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✓ Python 版本: $PYTHON_VERSION"

# 检查依赖
echo "✓ 检查依赖..."
python3 -c "from fastapi import FastAPI" 2>/dev/null && echo "  ✓ FastAPI"
python3 -c "import uvicorn" 2>/dev/null && echo "  ✓ Uvicorn"
python3 -c "from playwright.sync_api import sync_playwright" 2>/dev/null && echo "  ✓ Playwright"
python3 -c "from app.main import app" 2>/dev/null && echo "  ✓ 应用可加载"

# 检查数据文件
echo ""
echo "✓ 检查数据文件..."
test -f data/arbitrage.db && echo "  ✓ 数据库: data/arbitrage.db"
test -f data/cookies/1688_cookies.json && echo "  ✓ 1688 Cookies"
test -d data/categories && echo "  ✓ 类目映射数据 ($(ls data/categories/*.json | wc -l | tr -d ' ') 文件)"
test -d data/translations && echo "  ✓ 翻译词表 ($(ls data/translations/*.json | wc -l | tr -d ' ') 文件)"
test -d data/matcher && echo "  ✓ 匹配词典 ($(ls data/matcher/*.json | wc -l | tr -d ' ') 文件)"

# 检查端口
echo ""
echo "✓ 检查端口..."
if lsof -i :8000 > /dev/null 2>&1; then
    echo "  ⚠ 端口 8000 已被占用"
    echo "  服务可能已在运行: http://localhost:8000"
    echo "  或使用其他端口: uvicorn app.main:app --port 8001"
else
    echo "  ✓ 端口 8000 可用"
fi

echo ""
echo "=========================================="
echo "🚀 启动服务"
echo "=========================================="
echo ""
echo "方式 1: 开发模式 (推荐 - 自动重载)"
echo "  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "方式 2: 生产模式"
echo "  uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2"
echo ""
echo "方式 3: Docker"
echo "  docker-compose up -d"
echo ""
echo "=========================================="
echo "📊 测试链接"
echo "=========================================="
echo ""
echo "访问地址:"
echo "  • API 文档: http://localhost:8000/docs"
echo "  • 健康检查: http://localhost:8000/health"
echo "  • ReDoc: http://localhost:8000/redoc"
echo ""
echo "测试命令:"
echo "  • curl http://localhost:8000/health"
echo "  • pytest                    # 运行测试"
echo "  • pytest --cov=app          # 查看覆盖率"
echo ""
echo "=========================================="
