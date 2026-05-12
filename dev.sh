#!/bin/bash
# 开发服务器一键启动
# 用法: bash dev.sh

cd "$(dirname "$0")"

# 激活虚拟环境
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# 确保必要目录存在
mkdir -p data/cookies data/temp data/output logs

echo "🚀 启动 Amazon Arbitrage Agent..."
echo "    http://localhost:8000"
echo "    http://localhost:8000/docs (API 文档)"
echo ""

exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
