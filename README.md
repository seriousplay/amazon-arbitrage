# 🐾 Amazon Pet Arbitrage Scout

亚马逊宠物用品套利智能扫描系统 - 跨平台价差发现引擎

## 🚀 快速开始

### 本地开发

```bash
# 1. 克隆项目
cd ~/llm/amazon-pet-arbitrage

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt
playwright install chromium

# 4. 配置环境
cp .env.example .env
# 编辑 .env 修改配置

# 5. 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问：
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### Docker 部署

```bash
docker-compose up -d
```

## 📊 API 接口

### 扫描任务
- `POST /api/v1/scan/` - 启动扫描
- `GET /api/v1/scan/{task_id}` - 查询任务状态
- `POST /api/v1/scan/{task_id}/cancel` - 取消任务

### 结果查询
- `GET /api/v1/results/task/{task_id}` - 获取任务结果
- `GET /api/v1/results/latest?limit=20` - 最新结果

### 系统状态
- `GET /api/v1/status/tasks` - 所有任务列表
- `GET /api/v1/status/system` - 系统资源监控

## 🔧 核心特性

### 1️⃣ 三层反检测体系
- **Stealth 渲染器**：绕过 Cloudflare、PerimeterX
- **请求频率控制**：随机延迟（2-5 秒）
- **User-Agent 轮换**：每次请求随机 UA

### 2️⃣ 智能滑块破解
- **Layer 1**：智能元素定位（最快）
- **Layer 2**：纯视觉检测（OpenCV）
- **Layer 3**：贝塞尔轨迹模拟（拟人化）
- **Layer 4**：自动重试 + 降级策略

### 3️⃣ 三重登录管理
- **策略 1**：复用现有浏览器上下文
- **策略 2**：自动加载持久化 cookies
- **策略 3**：扫码登录（自动检测，无需按键）

### 4️⃣ 智能匹配与评分
```
综合分数 = 价差×0.4 + 销量×0.3 + 评分×0.2 + 竞争度×0.1
推荐阈值 ≥ 60 分（高置信度）
```

## 📁 项目结构

```
amazon-pet-arbitrage/
├── app/                          # 核心应用
│   ├── main.py                  # FastAPI 入口
│   ├── config.py                # 配置管理
│   ├── core/                    # 业务逻辑层
│   │   ├── scanner/             # 扫描工作流（模块化）
│   │   │   ├── __init__.py
│   │   │   ├── engine.py        # ScanOrchestrator
│   │   │   ├── task.py          # TaskManager
│   │   │   ├── discovery.py     # DiscoveryService
│   │   │   ├── matching.py      # MatchingService
│   │   │   ├── review.py        # ReviewWorkflow
│   │   │   ├── analysis.py      # AnalysisService
│   │   │   └── models.py        # 遗留类型定义
│   │   ├── alibaba/             # 1688 匹配（模块化）
│   │   │   ├── __init__.py
│   │   │   ├── matcher.py       # AlibabaMatcher Facade
│   │   │   ├── browser.py       # BrowserController
│   │   │   ├── captcha.py       # CaptchaSolver
│   │   │   └── search.py        # SearchHandler
│   │   ├── matcher/             # 模糊匹配（模块化）
│   │   │   ├── __init__.py
│   │   │   ├── matcher.py       # FuzzyMatcher
│   │   │   ├── synonyms.py      # SynonymManager
│   │   │   └── normalizer.py    # TextNormalizer
│   │   ├── scanner.py           # 扫描引擎（Legacy Facade）
│   │   ├── amazon_spider.py     # Amazon BSR 爬虫
│   │   ├── alibaba_matcher.py   # 1688 匹配器（Legacy Facade）
│   │   ├── scorer.py            # 匹配评分引擎
│   │   ├── rules.py             # 过滤规则
│   │   └── ...                  # 其他分析模块
│   ├── services/                # 服务层
│   │   ├── storage.py           # 数据库操作
│   │   └── browser_pool.py      # 浏览器池
│   ├── models/                  # 数据模型
│   │   ├── product.py           # Pydantic 模型
│   │   ├── mappers.py           # Pydantic ↔ ORM 转换
│   │   └── ...                  # 其他模型
│   ├── utils/                   # 工具模块
│   │   ├── translator.py        # 英中翻译
│   │   ├── category_mapper.py   # 类目映射
│   │   ├── fuzzy_matcher.py     # 模糊匹配
│   │   ├── slider_captcha.py    # 滑块验证码
│   │   └── ...                  # 其他工具
│   ├── api/v1/endpoints/        # REST API 路由
│   └── workers/                 # 后台任务
├── data/                        # 数据文件
│   ├── categories/              # 类目映射（355 条）
│   ├── translations/            # 翻译词表（438 条）
│   ├── matcher/                 # 匹配词典
│   └── cookies/                 # 1688 cookies
├── tests/                       # 测试套件
│   ├── unit/                    # 单元测试（128 tests）
│   └── integration/             # 集成测试（19 tests）
├── infrastructure/              # 部署配置
│   ├── docker/
│   └── nginx/
├── .github/workflows/           # CI/CD Pipeline
├── pyproject.toml               # 项目配置
├── .pre-commit-config.yaml      # Pre-commit hooks
├── DEVELOPMENT.md               # 开发指南
└── README.md                    # 本文档
```

## 🛠️ 开发指南

### 代码质量工具

本项目使用现代化的代码质量工具链：

- **Black** - 自动代码格式化
- **Ruff** - 快速代码检查（替代 flake8/isort）
- **Mypy** - 静态类型检查
- **Pytest** - 测试框架
- **pre-commit** - Git hooks 自动化

详细使用说明请参见 [DEVELOPMENT.md](DEVELOPMENT.md)

### 快速开始

```bash
# 安装 pre-commit hooks
pip install pre-commit
pre-commit install

# 运行所有检查
pre-commit run --all-files

# 运行测试
pytest

# 生成覆盖率报告
pytest --cov=app --cov-report=html
```

### 添加新的类目

编辑 `app/config.py` 中的 `CATEGORIES` 列表

### 调整评分权重

修改 `MatchScorer` 类中的权重系数

## 📈 监控与日志

- 日志文件：`logs/app.log`
- 数据库：`data/arbitrage.db`
- 调试截图：`data/temp/debug_*.png`

## ✅ 测试状态

- **总测试数**：147 tests
- **单元测试**：128 tests ✅
- **集成测试**：19 tests ✅
- **测试覆盖率**：26% overall, 70%+ for new modules
- **CI/CD**：GitHub Actions ✅

## ⚠️ 注意事项

1. **合规使用**：遵守 Amazon 和 1688 的 robots.txt
2. **频率控制**：避免高频请求导致 IP 封禁
3. **Cookies 安全**：不要提交 cookies 到版本控制
4. **商业使用**：需自行评估法律风险

## 📄 许可证

MIT License - 详见 LICENSE 文件

## 🙏 致谢

本项目的滑块破解技术参考了开源社区的多篇论文和实现：
- OpenCV 图像匹配算法
- Playwright 自动化测试框架
- FastAPI 现代化 Web 框架
