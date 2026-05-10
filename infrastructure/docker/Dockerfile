# Amazon Pet Arbitrage Scout - Docker 镜像（多阶段构建）
FROM python:3.11-slim AS builder

# 系统依赖（Playwright + OpenCV）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget gnupg unzip \
    libglib2.0-0 libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制并安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright Chromium
RUN playwright install chromium && playwright install-deps chromium

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p data/cookies data/temp data/output

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
