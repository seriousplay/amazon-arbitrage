# 开发工作流指南

## 代码质量工具

本项目使用以下工具确保代码质量：

### 1. Black - 代码格式化

自动格式化 Python 代码，保持一致的代码风格。

**配置**：`pyproject.toml` 中的 `[tool.black]` 部分
- 行长度：100 字符
- 目标版本：Python 3.10

**使用方法**：
```bash
# 检查哪些文件需要格式化
black --check --line-length=100 app/ tests/

# 自动格式化代码
black --line-length=100 app/ tests/
```

### 2. Ruff - 代码检查

快速 Python linter，替代 flake8/isort/pydocstyle。

**配置**：`pyproject.toml` 中的 `[tool.ruff]` 部分
- 目标版本：Python 3.10
- 行长度：100 字符
- 启用的规则：I (import sorting), F (pyflakes), E (pycodestyle), W (pycodestyle warnings)

**使用方法**：
```bash
# 检查代码
ruff check app/ tests/ --line-length=100

# 自动修复问题
ruff check app/ tests/ --fix --line-length=100
```

### 3. Mypy - 类型检查

静态类型检查器，基于 Python 类型提示。

**配置**：`pyproject.toml` 中的 `[tool.mypy]` 部分
- 忽略缺失导入（第三方库类型存根不完整）
- 排除测试、数据、日志目录

**使用方法**：
```bash
# 运行类型检查
mypy app/ --ignore-missing-imports
```

### 4. Pytest - 测试框架

**配置**：`pyproject.toml` 中的 `[tool.pytest.ini_options]` 部分
- 测试路径：`tests/`
- 异步模式：auto

**使用方法**：
```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/unit/test_scorer.py

# 运行特定测试
pytest tests/unit/test_scorer.py::TestMatchScorer::test_high_profit_score

# 显示覆盖率
pytest --cov=app --cov-report=term
```

## Pre-commit Hooks

Pre-commit 钩子在每次 git commit 前自动运行代码质量检查。

### 安装

```bash
# 安装 pre-commit
pip install pre-commit

# 安装 git hooks（只需运行一次）
pre-commit install
```

### 配置

配置文件：`.pre-commit-config.yaml`

**包含的钩子**：
1. **Black** - 自动格式化代码
2. **Ruff** - 自动修复并检查代码
3. **Mypy** - 类型检查（仅检查 app/ 目录）
4. **Pytest** - 运行测试（手动模式，使用 `pytest-check`）

### 使用

```bash
# 对所有文件运行 pre-commit（首次设置时）
pre-commit run --all-files

# 对已暂存的文件运行
pre-commit run

# 跳过 pre-commit 钩子（不推荐）
git commit --no-verify

# 手动运行特定钩子
pre-commit run black --all-files
pre-commit run ruff --all-files
```

### 跳过测试

pytest-check 钩子在 `stages: [manual]` 中，不会在每次 commit 时运行。要手动运行：

```bash
pre-commit run pytest-check --all-files
```

## CI/CD Pipeline (GitHub Actions)

### 工作流

文件：`.github/workflows/ci-cd.yml`

**触发条件**：
- Push 到 `main` 或 `develop` 分支
- Pull Request 到 `main` 分支

**Jobs**：

1. **lint** - 代码格式化和检查
   - Black 格式化检查
   - Ruff 代码检查

2. **type-check** - 类型检查
   - Mypy 静态类型分析

3. **test** - 测试套件
   - 在 Python 3.10, 3.11, 3.12 上运行测试
   - 生成覆盖率报告
   - 上传到 Codecov（仅 3.10 版本）

4. **security** - 安全扫描
   - Bandit - Python 安全漏洞扫描
   - Safety - 依赖安全检查

5. **build** - Docker 构建（仅 main 分支 push）
   - 构建 Docker 镜像
   - 推送到容器仓库（需配置）

### 状态徽章

在 README.md 中添加：

```markdown
![CI/CD](https://github.com/<owner>/<repo>/workflows/CI%2FCD%20Pipeline/badge.svg)
![Coverage](https://codecov.io/gh/<owner>/<repo>/branch/main/graph/badge.svg)
```

## 覆盖率报告

当前覆盖率：**26%** 整体，新模块 70%+

**核心模块覆盖率**：
- `scanner/discovery.py`: 100%
- `scanner/matching.py`: 91%
- `scanner/models.py`: 86%
- `scanner/review.py`: 94%
- `scorer.py`: 90%
- `translator.py`: 87%
- `category_mapper.py`: 74%

**覆盖率目标**：
- 新代码：> 80%
- 核心业务逻辑：> 70%
- 整体：逐步提升至 70%

## 开发工作流

### 推荐流程

1. **创建功能分支**
   ```bash
   git checkout -b feature/your-feature
   ```

2. **开发功能**
   - 编写代码
   - 添加测试
   - 本地运行测试：`pytest`
   - 本地运行 pre-commit：`pre-commit run --all-files`

3. **提交代码**
   ```bash
   git add .
   git commit -m "feat: add new feature"
   # pre-commit 钩子自动运行
   ```

4. **推送并创建 PR**
   ```bash
   git push origin feature/your-feature
   # 在 GitHub 创建 Pull Request
   ```

5. **CI/CD 自动运行**
   - GitHub Actions 运行所有检查
   - 等待所有 checks 通过
   - 代码审查
   - 合并到 main

## 已知问题

### 遗留代码类型错误

部分遗留文件存在类型检查错误，属于已知问题：
- `app/core/scanner.py` (526 行，旧版实现，即将移除)
- `app/utils/fuzzy_matcher.py` (正在迁移)
- `app/utils/renderer.py` (正在重构)

**策略**：新代码必须通过类型检查，旧代码逐步修复。

### Import 排序

部分文件 import 顺序不规范，将在后续迭代中逐步修复。

## 故障排除

### pre-commit 安装失败

```bash
# 确保使用正确的 Python 版本
python3 --version  # 应该 >= 3.10

# 升级 pip
python3 -m pip install --upgrade pip

# 重新安装 pre-commit
pip install pre-commit
```

### GitHub Actions 失败

1. 检查 Actions 日志
2. 本地复现：`pre-commit run --all-files`
3. 常见问题：
   - 格式化问题：运行 `black`
   - Linting 问题：运行 `ruff check --fix`
   - 测试失败：运行 `pytest -v`

### Mypy 误报

如果遇到第三方库类型问题：
```bash
# 检查是否有类型存根
pip install types-requests types-playwright

# 或者临时忽略（在 pyproject.toml 中添加到 exclude）
```

## 参考资源

- [Black 文档](https://black.readthedocs.io/)
- [Ruff 文档](https://docs.astral.sh/ruff/)
- [Mypy 文档](https://mypy.readthedocs.io/)
- [pre-commit 文档](https://pre-commit.com/)
- [GitHub Actions 文档](https://docs.github.com/cn/actions)
