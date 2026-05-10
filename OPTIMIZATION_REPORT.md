# Amazon Pet Arbitrage Scout — 代码审查与优化建议报告

**审查日期**：2026-05-08 | **审查范围**：全部项目代码

---

## 一、总体评估

项目采用 FastAPI + Playwright + SQLAlchemy + OpenCV 技术栈，整体分层架构（API → Core → Service）清晰合理。但存在若干代码缺陷、安全隐患和未完成模块，目前在功能完整度、生产就绪度和测试覆盖三方面均有较大提升空间。以下按严重程度分类列出问题和优化建议。

---

## 二、Bug（会导致运行时错误）

### 2.1 Amazon 爬虫使用 float 做列表切片 —TypeError

**文件**：`app/core/amazon_spider.py:54`

```python
items[:self.config.REQUEST_DELAY_MAX]  # REQUEST_DELAY_MAX 是 float 5.0
```

`REQUEST_DELAY_MAX` 是 `Field(default=5.0)`，用于请求延迟。这里错误地用作切片上限。Python `list[:5.0]` 会抛出 `TypeError`。

**修复**：应使用 `max_products` 参数或直接写成 `items[:max(5, len(items))]`。

### 2.2 匹配结果从未写入数据库

**文件**：`app/services/storage.py:57-77`

`save_scan_task` 方法接收 `results: List[dict]` 参数，但函数体内完全没有使用它——只保存了任务记录，匹配结果直接丢弃。

**修复**：需要创建 `match_results` 表并实现写入逻辑，或至少将结果序列化存入 JSON 字段。

### 2.3 产品模型使用 Pydantic v1 的 `validator` 装饰器

**文件**：`app/models/product.py:57`

```python
@validator('moq', pre=True, always=True)
```

项目依赖的是 `pydantic>=2.5.0`，但使用了 Pydantic v1 的 `@validator` API。Pydantic v2 中应使用 `@field_validator`，且参数签名不同。

**修复**：迁移到 Pydantic v2 API，或确认使用了 v1 兼容层。

### 2.4 Docker Compose 引用不存在的 Nginx 配置

**文件**：`docker-compose.yml:31`

```yaml
- ./infrastructure/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
```

`infrastructure/nginx/` 目录下只有 `__init__.py`，没有 `nginx.conf`。

### 2.5 `ScannerWorker.submit` 忽略传入的 task_id

**文件**：`app/workers/scanner_worker.py:31`

```python
async def submit(self, task_id: str, **kwargs):
    await self.scanner.start_scan(**kwargs)  # start_scan 内部生成新 task_id
```

`start_scan` 内部会调用 `uuid.uuid4()` 生成新 ID，完全忽略传入的 `task_id`。

---

## 三、架构问题

### 3.1 全局单例 + 模块级副作用

**涉及文件**：`app/api/v1/endpoints/scan.py`（`_scan_engine` 全局变量）、`app/api/v1/endpoints/results.py`（同上）、`app/config.py`（`os.makedirs` 在导入时执行）

- API 路由模块通过全局变量引用引擎，无法进行单元测试，且任何模块导入 `config.py` 都会触发目录创建。
- 已有的 FastAPI `app.state` 注入机制（`main.py` 中 `app.state.scanner`）完全被忽略。

**建议**：使用 FastAPI 的依赖注入（`Depends`）获取 `app.state.scanner`，或使用 `request.app.state`。配置模块中的 `os.makedirs` 应移到 `lifespan` 或惰性初始化。

### 3.2 AlibabaMatcher 硬编码外部技能路径

**文件**：`app/core/alibaba_matcher.py:10`

```python
SKILL_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent / ".hermes/skills/amazon-pet-arbitrage"
```

使用 6 层 `parent` 回溯到用户主目录下的特定路径，极具脆弱性——换一台机器或不同用户就无法运行。

**建议**：改为从环境变量或配置读取路径，或将所需代码直接内联到项目中。

### 3.3 每次调用都重新实例化匹配器

**文件**：`app/core/alibaba_matcher.py:27-34`

`search_and_match` 方法每次调用都执行动态 import 并创建新的 `OriginalMatcher` 实例。动态 import 开销大，且无法复用连接/状态。

**建议**：在 `__init__` 中初始化一次，缓存复用。

### 3.4 API 端点直接跨层引用 `app.main`

**文件**：`app/api/v1/endpoints/status.py:6`

```python
from app.main import app
```

这形成了循环依赖的风险（`main.py` 导入路由，路由导入 `main.py`）。`status.py` 直接访问 `app.state` 绕过依赖注入。

### 3.5 AlibabaProduct 模型字段冗余

**文件**：`app/models/product.py:47-48`

```python
min_order_qty: int = Field(..., gt=0, description="起订量")
moq: int = Field(..., alias="moq", description="MOQ（同 min_order_qty）")
```

两个字段映射同一概念，validator 的逻辑容易在序列化/反序列化时产生混乱。

**建议**：只保留一个字段（如 `min_order_qty`），在需要时添加 `moq` 作为 `computed_field` 或属性。

---

## 四、安全隐患

### 4.1 零认证机制

整个 API 没有任何认证（JWT、API Key、OAuth2 均无）。任何能访问 8000 端口的人都可以触发爬虫任务。CHECKLIST.md 已标注"待办"。

**建议**：优先级最高。至少添加简单的 API Key 认证，推荐使用 FastAPI 的 `HTTPBearer` + JWT。

### 4.2 CORS 配置过于宽松

**文件**：`app/config.py:23`

```python
ALLOWED_ORIGINS: list = Field(default=["*"])
```

允许任意来源跨域请求，且 credential 为 True。这违反了安全最佳实践（CORS 规范中 `Access-Control-Allow-Origin: *` 与 `credentials: true` 不能并存）。

**建议**：生产环境显式配置允许的域名列表。

### 4.3 无速率限制

无任何限流机制，攻击者可以无限提交扫描任务消耗资源。且爬虫请求延迟对 1688 的 rate limit 保护不足。

**建议**：集成 `slowapi` 或 Redis 令牌桶，对 `/api/v1/scan/` 端点实施限流。

### 4.4 CAPTCHA_DEBUG 在生产环境开启

**文件**：`.env.example:28`

```python
CAPTCHA_DEBUG=true
```

滑块破解的调试截图可能包含敏感页面内容，在生产环境泄露会有隐私风险。

**建议**：生产环境设为 false，且不保存到可公开访问的目录。

---

## 五、性能问题

### 5.1 扫描流程全串行

**文件**：`app/core/scanner.py:107-132`

匹配阶段逐个处理 Amazon 商品，每个都要等待 1688 搜索完成。如果有 10 个商品，每个搜索耗时 30 秒，总耗时达 5 分钟。

**建议**：使用 `asyncio.Semaphore` 控制并发，对多个商品同时匹配。例如 3 个并发匹配可将时间压缩到约 1/3。

### 5.2 无响应缓存

Amazon BSR 榜单短时间内不会变化，但每次扫描都要重新爬取。

**建议**：添加 TTL 缓存（如 15 分钟的 `cachetools.TTLCache` 或 Redis），缓存已爬取的 BSR 页面和 1688 搜索结果。

### 5.3 StorageService 双引擎开销

**文件**：`app/services/storage.py:42-53`

同时创建同步引擎（用于 `create_all`）和异步引擎（用于查询）。同步引擎仅在初始化时创建表，之后闲置。

**建议**：使用 `run_sync` 在异步引擎上执行 DDL，或直接用 Alembic 管理迁移。

### 5.4 `asyncio.to_thread` 阻塞事件循环线程池

**文件**：`app/core/alibaba_matcher.py:41`

每次 1688 搜索都用 `asyncio.to_thread` 包装。默认线程池只有 `min(32, os.cpu_count() + 4)` 个线程，高频调用可能耗尽。

**建议**：使用专用 `ThreadPoolExecutor`，或改为纯异步实现。

---

## 六、代码质量

### 6.1 缺少类型注解一致性

- `amazon_spider.py` 大部分有注解但 `scraper.py` 的 `config` 参数无类型。
- `storage.py` 的 `save_scan_task` 返回 `None` 但无注解。
- `scorer.py` 的 `score_match` 返回值有注解但 `_get_recommendation` 无。

**建议**：启用 `mypy` / `pyright` 严格模式，补充完整类型注解。

### 6.2 错误处理过于宽泛

多处使用裸 `except Exception` 或 `except:`（`alibaba_matcher.py:66,74`），吞掉所有异常信息。

**建议**：至少记录异常栈（`exc_info=True`），对可恢复的错误重试，对不可恢复的错误明确终止。

### 6.3 日志文件在 DEBUG 级别记录生产日志

**文件**：`app/utils/logger.py:28`

文件日志固定为 `DEBUG` 级别，在生产环境会产生大量日志文件。

**建议**：根据 `ENVIRONMENT` 配置决定日志级别。

### 6.4 使用已废弃的 Pydantic API

**文件**：`app/api/v1/endpoints/results.py:36`

```python
results = [r.dict() for r in task.results]
```

Pydantic v2 中 `.dict()` 已废弃，应使用 `.model_dump()`。

### 6.5 `get_logger` 每次调用创建新的 `bind`

**文件**：`app/utils/logger.py:10`

```python
return logger.bind(name=name)
```

每次调用创建新绑定，但 `get_logger(__name__)` 被多处调用，可考虑缓存 logger 实例。

### 6.6 docs 目录下有 `__init__.py`

`docs/__init__.py` 不应存在，docs 不是 Python 包。

---

## 七、测试与 CI

### 7.1 零测试覆盖

`tests/unit/` 和 `tests/integration/` 下只有空的 `__init__.py`，没有任何测试用例。

**建议**：至少添加以下核心测试：
- `AmazonProduct` / `AlibabaProduct` 模型验证测试
- `MatchScorer.score_match` 单元测试（边界值、负价差）
- `ScanEngine` 集成测试（mock HTTP 响应）
- API 端点 smoke test

### 7.2 缺乏 CI 配置

没有 `.github/workflows/` 或任何 CI 配置。

**建议**：添加 GitHub Actions 流水线，至少包含 lint（ruff/black）、type check（mypy）、test（pytest）、security scan（bandit）。

---

## 八、依赖与构建

### 8.1 pyproject.toml 与 requirements.txt 不一致

`requirements.txt` 包含但 `pyproject.toml` 缺失的依赖：`alembic`、`lxml`、`Pillow`、`python-dotenv`、`tenacity`、`aiofiles`、`psutil`、`prometheus-client`。

**建议**：以 `pyproject.toml` 为唯一依赖声明源，`requirements.txt` 可由 `pip-compile` 生成锁定版本。

### 8.2 Dockerfile 重复安装 Playwright

**文件**：`infrastructure/docker/Dockerfile:38-43`

```dockerfile
RUN pip install --no-cache-dir -r requirements.txt  # 包含 playwright
RUN pip install --no-cache-dir playwright  # 再次安装
```

第二次安装是冗余的。

### 8.3 无多阶段构建

Docker 镜像会包含所有构建依赖和源代码，最终镜像偏大。

**建议**：使用多阶段构建，构建阶段安装依赖，运行阶段只复制必要文件。

### 8.4 venv 目录可能过大

`venv/` 下的 `site-packages` 包含 `__pycache__` 和大量非必要文件。确保 `.gitignore` 中的 `venv/` 规则生效。

---

## 九、功能缺失

按 CHECKLIST.md 标注的优先级：

**优先级 1（核心功能缺失）**：
- `alibaba_matcher.py` 仅为包装器，完整实现约 1100 行代码未迁移
- `renderer.py`（Stealth 渲染器 503 行）未集成
- `slider_captcha.py`（异步滑块破解 190 行）未完整集成

**优先级 2（生产就绪）**：
- JWT 认证未实现
- 速率限制未实现
- Sentry 错误监控未集成
- Prometheus 指标未暴露

**当前实际可运行的功能**：仅 Amazon BSR 爬取和评分计算（且爬虫有 bug），1688 匹配依赖外部代码路径。

---

## 十、优化优先级路线图

| 优先级 | 类别 | 具体事项 | 预估工作量 |
|--------|------|----------|-----------|
| P0 | Bug | 修复 `amazon_spider.py` float 切片 | 5 分钟 |
| P0 | Bug | 实现 `save_scan_task` 结果写入 | 1 小时 |
| P0 | 架构 | 迁移 AlibabaMatcher 完整实现到项目内 | 4 小时 |
| P0 | 配置 | 修复 docker-compose 缺失的 nginx.conf | 30 分钟 |
| P1 | 安全 | 添加 API Key / JWT 认证 | 2 小时 |
| P1 | 安全 | 添加请求速率限制 | 1 小时 |
| P1 | 性能 | 匹配阶段改为并行处理 | 1 小时 |
| P1 | 修复 | Pydantic v1 → v2 迁移 | 1 小时 |
| P2 | 质量 | 补充类型注解 + mypy 检查 | 2 小时 |
| P2 | 测试 | 编写核心流程单元测试 | 3 小时 |
| P2 | CI | 添加 GitHub Actions 流水线 | 1 小时 |
| P3 | 性能 | 添加 BSR 结果缓存层 | 2 小时 |
| P3 | 运维 | Docker 多阶段构建优化 | 1 小时 |
| P3 | 可靠性 | 添加重试/退避机制 | 1 小时 |

**总预估工数**：约 3-4 个工作日可达到生产可用状态（P0+P1）。
