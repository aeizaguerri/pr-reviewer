"""Backend health checks used by Render deploys."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app
from src.core.config import Config


class TestHealthEndpoint:
    def test_root_health_path_is_available_for_render(self, monkeypatch):
        monkeypatch.setattr(Config, "ENABLE_GRAPH_ENRICHMENT", False)

        with TestClient(app) as client:
            response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "neo4j": False}

    def test_api_health_skips_neo4j_when_graph_enrichment_disabled(self, monkeypatch):
        monkeypatch.setattr(Config, "ENABLE_GRAPH_ENRICHMENT", False)

        with patch("src.knowledge.client.check_health") as mock_check_health:
            with TestClient(app) as client:
                response = client.get("/api/v1/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "neo4j": False}
        mock_check_health.assert_not_called()

    def test_api_health_checks_neo4j_when_graph_enrichment_enabled(self, monkeypatch):
        monkeypatch.setattr(Config, "ENABLE_GRAPH_ENRICHMENT", True)

        with patch("src.knowledge.client.check_health", return_value=True) as mock_check_health:
            with TestClient(app) as client:
                response = client.get("/api/v1/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "neo4j": True}
        mock_check_health.assert_called_once_with()
