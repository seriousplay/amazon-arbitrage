#!/bin/bash
# ============================================================
# Amazon Pet Arbitrage Scout - 一键部署 & 测试脚本
# 用法: bash run.sh [test|deploy|all]
# ============================================================
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ─── 安装依赖 ────────────────────────────────────────────
install_deps() {
    log "检查 Python 版本..."
    python3 --version || err "需要 Python 3.10+"

    if [ ! -d "venv" ]; then
        log "创建虚拟环境..."
        python3 -m venv venv
    fi

    source venv/bin/activate
    log "安装项目依赖..."
    pip install -e ".[dev]" -q 2>&1 | tail -3

    log "安装 Playwright 浏览器..."
    playwright install chromium 2>&1 | tail -3

    log "依赖安装完成"
}

# ─── 运行测试 ────────────────────────────────────────────
run_tests() {
    log "正在激活虚拟环境..."
    source venv/bin/activate 2>/dev/null || true

    log "运行离线验证脚本（无需外部依赖）..."
    python3 tests/run_validation.py

    if python3 -c "import pytest" 2>/dev/null; then
        log "运行 pytest 单元测试..."
        python3 -m pytest tests/unit/ -v --tb=short 2>&1
    else
        warn "pytest 未安装，跳过 pytest 测试（先运行: bash run.sh install）"
    fi
}

# ─── 启动开发服务器 ──────────────────────────────────────
start_dev() {
    log "启动开发服务器..."
    source venv/bin/activate 2>/dev/null || {
        warn "venv 未找到，使用系统 Python"
    }

    # 确保目录存在
    mkdir -p data/cookies data/temp data/output logs

    # 创建 .env（如果不存在）
    if [ ! -f .env ]; then
        cp .env.example .env
        log "已创建 .env（从 .env.example）"
    fi

    log "启动 uvicorn http://localhost:8000 ..."
    python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
}

# ─── Docker 部署 ──────────────────────────────────────────
docker_deploy() {
    log "Docker 构建 & 启动..."
    docker-compose build --no-cache
    docker-compose up -d
    sleep 3
    log "检查健康状态..."
    curl -s http://localhost:8000/health | python3 -m json.tool
    log "部署完成: http://localhost:8000/docs"
}

# ─── 主逻辑 ──────────────────────────────────────────────
case "${1:-all}" in
    install)
        install_deps
        ;;
    test)
        run_tests
        ;;
    dev)
        install_deps
        start_dev
        ;;
    deploy)
        docker_deploy
        ;;
    all|*)
        log "=== Amazon Pet Arbitrage Scout ==="
        log ""
        log "1. 安装依赖 + 运行测试..."
        install_deps
        echo ""
        log "2. 运行测试..."
        run_tests
        echo ""
        log "3. 启动开发服务器..."
        echo ""
        echo "  运行 'bash run.sh dev' 启动服务器"
        echo "  运行 'bash run.sh deploy' Docker 部署"
        echo "  运行 'bash run.sh test' 仅测试"
        ;;
esac
