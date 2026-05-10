# 系统架构

## 分层架构

- **应用层**：FastAPI + 路由
- **核心层**：ScanEngine + AmazonBSRSpider + AlibabaMatcher + MatchScorer
- **服务层**：StorageService + BrowserPool + CaptchaSolver
- **基础设施**：Playwright + SQLAlchemy + OpenCV

## 核心流程

扫描 → 爬取 → 匹配 → 评分 → 保存
