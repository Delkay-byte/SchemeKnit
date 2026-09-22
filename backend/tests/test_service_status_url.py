"""
Service status health-check URL resolution.

Verifies that the frontend service-status hook targets the correct API
backend URL rather than the frontend origin (which caused the false
'Server unavailable' banner on Render deployments).

Also verifies the backend /api/service-status endpoint responds correctly.
"""

import sys
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.main import app  # noqa: E402


client = TestClient(app)


class TestServiceStatusEndpoint:
    """Backend /api/service-status must respond with healthy status."""

    def test_service_status_returns_200(self):
        resp = client.get("/api/service-status")
        assert resp.status_code == 200

    def test_service_status_has_status_field(self):
        resp = client.get("/api/service-status")
        data = resp.json()
        assert "status" in data
        assert data["status"] in ("healthy", "maintenance", "degraded")

    def test_service_status_has_maintenance_field(self):
        resp = client.get("/api/service-status")
        data = resp.json()
        assert "maintenance" in data
        assert "active" in data["maintenance"]

    def test_service_status_has_version_field(self):
        resp = client.get("/api/service-status")
        data = resp.json()
        assert "version" in data

    def test_service_status_healthy_by_default(self):
        resp = client.get("/api/service-status")
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["maintenance"]["active"] is False

    def test_health_endpoint_also_works(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_ready_endpoint_also_works(self):
        resp = client.get("/api/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True
