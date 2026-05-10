# 快速参考卡

## 启动命令

### 开发模式
```bash
cd /Users/heyiqing/llm/amazon-pet-arbitrage
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### 生产模式
```bash
docker-compose up -d
```

## API 速查

| 端点 | 方法 | 用途 |
|-------|------|------|
| `/` | GET | 应用信息 |
| `/health` | GET | 健康检查 |
| `/api/v1/scan/` | POST | 启动扫描 |
| `/api/v1/results/task/{id}` | GET | 查询结果 |
| `/api/v1/status/tasks` | GET | 所有任务 |
| `/docs` | GET | Swagger UI |

## 目录结构速查

```
amazon-pet-arbitrage/
├── app/                    # 核心代码
│   ├── main.py            # FastAPI 入口
│   ├── config.py          # 配置（.env）
│   ├── core/              # 业务逻辑
│   │   ├── scanner.py     # 扫描引擎
│   │   ├── amazon_spider.py
│   │   ├── alibaba_matcher.py  ← 滑块破解
│   │   └── scorer.py
│   ├── services/          # 服务层
│   │   └── storage.py     # 数据库
│   └── api/               # REST API
├── data/                  # 数据目录（gitignore）
│   ├── cookies/           # 1688 cookies（重要！）
│   ├── temp/              # 调试截图
│   └── output/            # 报告输出
├── infrastructure/        # 部署配置
│   ├── docker/Dockerfile
│   └── nginx/nginx.conf
├── logs/                  # 应用日志
└── requirements.txt       # Python 依赖
```

## 关键配置（.env）

```bash
# 爬虫
REQUEST_DELAY_MIN=2.0
REQUEST_DELAY_MAX=5.0

# 滑块破解
SLIDER_USE_VISION=true
CAPTCHA_DEBUG=true

# 评分
MIN_SCORE_FOR_RECOMMENDATION=60

# 并发
MAX_WORKERS=2
```

## 调试技巧

### 查看实时日志
```bash
tail -f logs/app-$(date +%Y-%m-%d).log
```

### 检查数据库
```bash
sqlite3 data/arbitrage.db "SELECT * FROM scan_tasks ORDER BY created_at DESC LIMIT 5;"
```

### 测试滑块破解（单独）
```python
from app.core.alibaba_matcher import AlibabaMatcher
matcher = AlibabaMatcher(auto_mode=False)
matcher._ensure_login_with_renderer()  # 会打开浏览器
```

### 查看调试截图
```bash
open data/temp/*.png  # macOS
```

## 故障排查

| 问题 | 解决 |
|------|------|
| 浏览器启动失败 | `playwright install chromium` |
| cookies 无效 | 删除 `data/cookies/*.json` 重新扫码 |
| 内存过高 | 降低 `MAX_WORKERS=1` |
| 扫描太慢 | 调整 `REQUEST_DELAY_MAX=3.0` |
| 滑块破解失败 | 检查 `data/temp/slider_*.png` 调试图 |

## 性能基准

- **单任务扫描**：约 3-5 分钟（2 个商品）
- **并发任务**：最多 2 个同时运行
- **成功率**：>85%（有有效 cookies）
- **数据库大小**：< 10 MB（1000 条记录）

## 下一步开发

1. ✅ 基础 API 完成
2. ⏳ 集成原技能完整滑块破解
3. ⏳ WebSocket 实时推送
4. ⏳ 前端管理界面
5. ⏳ 分布式爬虫（Celery）
6. ⏳ 多平台支持（eBay/Walmart）

## 联系支持

- Issues: 提交到项目仓库
- 文档: `/Users/heyiqing/llm/amazon-pet-arbitrage/docs/`
