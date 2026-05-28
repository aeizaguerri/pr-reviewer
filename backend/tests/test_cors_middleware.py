"""Backend startup tests for CORS middleware configuration."""

import importlib

from fastapi.testclient import TestClient

from src.core.config import Config


def _reload_main_with_cors(monkeypatch, cors_value):
    monkeypatch.setattr(Config, "CORS_ORIGINS", cors_value)
    import backend.main as main_module
    importlib.reload(main_module)
    # Prevent side effects during lifespan in the reloaded module
    monkeypatch.setattr(main_module, "configure_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "configure_opik", lambda: None)
    monkeypatch.setattr(main_module, "warm_prompt_cache", lambda names: None)
    monkeypatch.setattr(main_module.Config, "validate", lambda: None)
    return main_module


class TestCorsMiddleware:
    """Verify CORS middleware reads config-derived origins during startup."""

    def test_cors_defaults_to_star_allowing_any_origin(self, monkeypatch):
        main_module = _reload_main_with_cors(monkeypatch, "*")
        with TestClient(main_module.app) as client:
            response = client.options(
                "/health",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )
        # With allow_credentials=True and origins="*", middleware mirrors the request origin
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_cors_respects_env_override_for_specific_origin(self, monkeypatch):
        main_module = _reload_main_with_cors(monkeypatch, "http://localhost:3000")
        with TestClient(main_module.app) as client:
            response = client.options(
                "/health",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_cors_blocks_non_allowed_origin_when_override_set(self, monkeypatch):
        main_module = _reload_main_with_cors(monkeypatch, "http://localhost:3000")
        with TestClient(main_module.app) as client:
            response = client.options(
                "/health",
                headers={
                    "Origin": "http://evil.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
        assert "access-control-allow-origin" not in response.headers
