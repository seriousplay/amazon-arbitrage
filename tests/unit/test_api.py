"""
API 端点 smoke test
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def test_app(mock_config, mock_storage):
    """创建带 mock 依赖的 FastAPI 测试实例"""
    from app.main import app

    app.state.storage = mock_storage
    # scanner 需要 mock
    scanner = MagicMock()
    scanner.start_scan = AsyncMock(return_value="test-task-01")
    scanner.get_task = MagicMock(return_value=None)
    scanner.list_tasks = MagicMock(return_value=[])
    app.state.scanner = scanner

    worker = MagicMock()
    worker.is_running = True
    app.state.worker = worker

    return app


class TestRootEndpoints:
    def test_root(self, test_app):
        client = TestClient(test_app)
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert "docs" in data

    def test_health(self, test_app):
        client = TestClient(test_app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"


class TestScanEndpoints:
    def test_start_scan(self, test_app):
        client = TestClient(test_app)
        resp = client.post("/api/v1/scan/?category=Dogs&max_products=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["task_id"] == "test-task-01"

    def test_cancel_nonexistent_task(self, test_app):
        client = TestClient(test_app)
        resp = client.post("/api/v1/scan/nonexistent/cancel")
        assert resp.status_code == 404


class TestStatusEndpoints:
    def test_list_tasks_empty(self, test_app):
        client = TestClient(test_app)
        resp = client.get("/api/v1/status/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tasks"] == []
        assert data["total"] == 0

    def test_system_status(self, test_app):
        client = TestClient(test_app)
        resp = client.get("/api/v1/status/system")
        assert resp.status_code == 200
        data = resp.json()
        assert "cpu_percent" in data
        assert "memory" in data


class TestResultsEndpoints:
    def test_get_task_not_found(self, test_app):
        client = TestClient(test_app)
        resp = client.get("/api/v1/results/task/nonexistent")
        assert resp.status_code == 404

    def test_get_latest(self, test_app, mock_storage):
        mock_storage.list_recent_tasks = AsyncMock(
            return_value=[
                {
                    "id": "t1",
                    "category": "Dogs",
                    "amazon_count": 10,
                    "match_count": 3,
                    "status": "completed",
                    "created_at": "2026-01-01T00:00:00",
                }
            ]
        )
        client = TestClient(test_app)
        resp = client.get("/api/v1/results/latest?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
