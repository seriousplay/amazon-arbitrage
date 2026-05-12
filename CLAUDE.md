# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Amazon Pet Arbitrage Scout** — 亚马逊宠物用品套利智能扫描系统

A Python-based web application that discovers arbitrage opportunities between Amazon and 1688 (Alibaba) for pet supplies. The system uses browser automation with sophisticated anti-detection techniques to scrape product data and score potential matches.

## Tech Stack

- **Framework**: FastAPI + Uvicorn
- **Database**: SQLite with SQLAlchemy 2.0 + AIOSQLite
- **Browser Automation**: Playwright (Chromium)
- **Image Processing**: OpenCV, Pillow
- **Testing**: pytest + pytest-asyncio
- **Config**: Pydantic Settings (environment variables)
- **Logging**: Loguru
- **Deployment**: Docker + Docker Compose + Nginx

## Project Structure

```
app/
├── main.py                    # FastAPI application entry point
├── config.py                  # Pydantic settings / environment config
├── core/                      # Business logic layer
│   ├── scanner.py            # Main scan engine (873 lines)
│   ├── alibaba_matcher.py    # 1688 browser automation & matching (790 lines)
│   ├── amazon_spider.py      # Amazon BSR spider
│   ├── scorer.py             # Match scoring engine (131 lines)
│   ├── scheduler.py          # Background task scheduler
│   ├── rules.py              # Filtering rules configuration
│   ├── breakout_scorer.py    # Product breakout detection
│   ├── concentration.py      # Market concentration analysis
│   ├── newproduct.py         # New product analysis
│   ├── review_crawler.py     # Review data collection
│   ├── review_analyzer.py    # Review sentiment analysis
│   ├── trends.py             # Trend analysis engine
│   └── risk_assessor.py      # Risk assessment
├── api/v1/endpoints/          # REST API routes
│   ├── scan.py               # Scan task management
│   ├── results.py            # Results & category queries
│   └── status.py             # System status
├── services/                  # Service layer
│   ├── storage.py            # Database operations
│   └── browser.py            # Browser pool management
├── models/                    # Pydantic data models
│   ├── product.py            # AmazonProduct, AlibabaProduct, MatchResult
│   ├── match.py              # Match-related models
│   ├── review.py             # Review models
│   ├── trend.py              # Trend models
│   └── concentration.py      # Concentration models
├── workers/                   # Background workers
│   └── scanner_worker.py     # Async task executor
├── utils/                     # Utilities
│   ├── slider_captcha.py     # Captcha solving (4-layer strategy)
│   ├── trajectory.py         # Bezier curve simulation
│   ├── translator.py         # CN/EN translation
│   ├── category_mapper.py    # Category mapping
│   ├── fuzzy_matcher.py      # Fuzzy string matching
│   ├── anti_block.py         # Anti-blocking strategies
│   ├── renderer.py           # Stealth browser renderer
│   ├── upc_lookup.py         # UPC lookup
│   ├── retry.py              # Retry utilities
│   ├── image_processing.py   # Image utilities
│   └── logger.py             # Logging setup
└── static/                    # Frontend assets
```

## Common Development Tasks

### Environment Setup

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium
```

### Running the Application

```bash
# Development mode with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/unit/test_scorer.py

# Run specific test class/method
pytest tests/unit/test_scorer.py::TestMatchScorer::test_high_profit_score

# Run with coverage
pytest --cov=app

# Run async tests (pytest-asyncio is configured in pyproject.toml)
pytest tests/ -v
```

### Code Quality

```bash
# Format code with Black
black app/ tests/

# Lint with Ruff
ruff check app/ tests/
ruff check --fix app/ tests/

# Type checking (if mypy configured)
mypy app/
```

### Docker Deployment

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop services
docker-compose down

# Rebuild after code changes
docker-compose up -d --build
```

### Initial Setup Steps

```bash
# 1. Copy environment configuration
cp .env.example .env
# Edit .env as needed

# 2. Create required directories
mkdir -p data/cookies data/temp data/output logs

# 3. Get 1688 cookies (required for matching)
python scripts/save_1688_cookies.py
# Opens browser → login to 1688 → press Enter to save cookies
```

## Architecture Overview

### Core Workflow: Three-Phase Scan

1. **Discovery Phase** — Amazon BSR Spider crawls Best Sellers Rank pages to discover products
2. **Review Phase** — Human-in-the-loop approval (optional filtering)
3. **Matching Phase** — AlibabaMatcher searches 1688 for sourcing options

```
AmazonBSRSpider → AmazonProduct
         ↓
    ScanEngine (filter by rules)
         ↓
    Human Review (optional)
         ↓
    AlibabaMatcher → AlibabaProduct
         ↓
    MatchScorer → MatchResult (0-100 score)
         ↓
    StorageService → Database
```

### Key Components

**ScanEngine** (`app/core/scanner.py`)
- Orchestrates the entire scan workflow
- Manages scan tasks and their lifecycle
- Coordinates between discovery, review, and matching phases
- Integrates with background worker pool

**AmazonBSRSpider** (`app/core/amazon_spider.py`)
- Scrapes Amazon Best Sellers Rank pages
- Extracts product data (ASIN, title, price, rating, reviews)
- Uses stealth rendering to avoid detection

**AlibabaMatcher** (`app/core/alibaba_matcher.py`)
- Browser automation for 1688.com search
- 4-layer captcha solving strategy:
  1. Smart element locator (fastest)
  2. Pure vision detection (OpenCV)
  3. Bezier trajectory simulation (human-like)
  4. Auto-retry with fallback
- Global browser singleton pattern (single Chromium instance)
- Requires saved cookies for authentication

**MatchScorer** (`app/core/scorer.py`)
- Calculates arbitrage score (0-100)
- Weighted formula:
  - Price difference: 40%
  - Sales volume (reviews): 30%
  - Rating: 20%
  - Competition: 10%
- Considers: CNY/USD rate, shipping costs, MOQ, profit margin

**StorageService** (`app/services/storage.py`)
- Async SQLAlchemy database operations
- SQLite by default, configurable via DATABASE_URL
- Stores scan tasks, products, and match results

**ScannerWorker** (`app/workers/scanner_worker.py`)
- Background task executor using asyncio
- Limits concurrent tasks (MAX_WORKERS config)
- Processes scan queue asynchronously

### Configuration Management

All configuration via environment variables loaded by Pydantic Settings:
- See `app/config.py` for all available settings
- Default values defined in Settings class
- `.env` file for local overrides (git-ignored)
- `.env.example` provides template

### Database Schema

Key tables (managed by SQLAlchemy + Alembic):
- `scan_tasks` — Scan job metadata and status
- `products` — Amazon products discovered
- `match_results` — Amazon-1688 matches with scores
- (Additional tables for reviews, trends, etc.)

### API Endpoints

**Scan Management**
- `POST /api/v1/scan/` — Start new scan task
- `GET /api/v1/scan/{task_id}` — Get task status
- `POST /api/v1/scan/{task_id}/cancel` — Cancel running task

**Results**
- `GET /api/v1/results/task/{task_id}` — Full task results with products
- `GET /api/v1/results/latest?limit=20` — Recent scan results
- `GET /api/v1/results/categories` — Available product categories

**Status**
- `GET /api/v1/status/tasks` — List all tasks
- `GET /api/v1/status/system` — System resource monitoring

**Rules**
- `GET /api/v1/scan/rules` — Get current filter rules
- `POST /api/v1/scan/rules` — Update filter rules
- `GET /api/v1/scan/rules/presets` — List rule presets
- `POST /api/v1/scan/rules/presets/{id}` — Apply preset rules

## Important Development Notes

### Anti-Detection Architecture

The system employs multiple layers to avoid bot detection:
- **Stealth renderer** with Playwright stealth plugin
- **User-Agent rotation** with realistic browser fingerprints
- **Random request delays** (configurable 2-5 seconds default)
- **Cookie persistence** for session management
- **Browser context reuse** to minimize fingerprint changes
- **Visual captcha solving** using OpenCV image matching

### Browser Management

- Global browser singleton pattern (one Chromium instance)
- `asyncio.Semaphore(1)` controls browser access
- Cookies stored in `data/cookies/1688_cookies.json`
- Use `scripts/save_1688_cookies.py` to obtain fresh cookies

### Async Architecture

- FastAPI async routes
- All I/O operations are async (database, HTTP, Playwright)
- Background tasks run in worker pool with semaphore control
- Database uses aiosqlite for async operations

### Testing Strategy

- Unit tests use pytest with mocked async dependencies
- `tests/conftest.py` provides fixtures for mock config and storage
- Integration tests require Playwright setup
- Test isolation with SQLite in-memory or temp databases

## Key Files Reference

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app, routes, lifespan management |
| `app/config.py` | All configuration settings and defaults |
| `app/core/scanner.py` | Main orchestration engine |
| `app/core/alibaba_matcher.py` | 1688 browser automation + captcha solving |
| `app/core/scorer.py` | Match scoring algorithm |
| `app/services/storage.py` | Database layer |
| `requirements.txt` | Python dependencies |
| `pyproject.toml` | Project metadata + tool configs (pytest, black, ruff) |
| `docker-compose.yml` | Production deployment |
| `infrastructure/docker/Dockerfile` | Container image definition |
| `.env.example` | Environment variable template |

## Debugging

### View Logs

```bash
tail -f logs/app-$(date +%Y-%m-%d).log
```

### Check Database

```bash
sqlite3 data/arbitrage.db "SELECT * FROM scan_tasks ORDER BY created_at DESC LIMIT 5;"
```

### Debug Captcha Solving

- Screenshots saved to `data/temp/slider_*.png` when `CAPTCHA_DEBUG=true`
- Inspect images to understand why captcha solving failed

### Test 1688 Matching Standalone

```python
from app.core.alibaba_matcher import AlibabaMatcher
matcher = AlibabaMatcher()
await matcher._ensure_browser()
# Manually test search functionality
```

### Inspect Running Tasks

```bash
# Get task details via API
curl http://localhost:8000/api/v1/results/task/{task_id}
```

## Environment Variables (Key Ones)

```bash
# Application
ENVIRONMENT=development|production
DEBUG=false

# Database
DATABASE_URL=sqlite+aiosqlite:///data/arbitrage.db

# Playwright/Browser
PLAYWRIGHT_HEADLESS=false
PLAYWRIGHT_TIMEOUT=30000
BROWSER_CONCURRENCY=2

# Scraping
REQUEST_DELAY_MIN=2.0
REQUEST_DELAY_MAX=5.0

# Scoring
MIN_SCORE_FOR_RECOMMENDATION=60
PRICE_DIFF_WEIGHT=0.4
SALES_WEIGHT=0.3
RATING_WEIGHT=0.2
COMPETITION_WEIGHT=0.1

# Concurrency
MAX_WORKERS=2
```

## Performance Characteristics

- Single scan task: ~3-5 minutes (2 products with default settings)
- Max concurrent tasks: 2 workers
- Success rate: >85% with valid 1688 cookies
- Database: <10MB per 1000 records
- Browser memory: ~200-300MB per Chromium instance

## Important Constraints

- **Python 3.10+** required (uses modern typing features)
- **1688 cookies** required for matching functionality
- **Playwright Chromium** must be installed
- Rate limiting is critical to avoid IP bans
- Browser automation requires significant memory
