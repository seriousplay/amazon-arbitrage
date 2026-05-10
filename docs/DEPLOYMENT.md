# 部署指南

## 本地开发
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload
```

## Docker
```bash
docker-compose up -d
```
