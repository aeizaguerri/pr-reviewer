"""Integration tests: POST /api/v1/review endpoint — header-based auth.

Phase 4 (RED): Tests written BEFORE the implementation.
These tests define the expected contract for Fix 2 (credential transport via HTTP headers).

Phase 5 (GREEN): All tests pass after routes.py / schemas.py / reviewer.py are updated.
"""

from unittest.mock import ANY, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.schemas import ReviewResponse

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

REVIEW_URL = "/api/v1/review"

VALID_BODY = {
    "owner": "o",
    "repo": "r",
    "pr_number": 1,
}

MOCK_REVIEW_RESPONSE = ReviewResponse(
    summary="LGTM",
    approved=True,
    bugs=[],
    impact_warnings=[],
)


@pytest.fixture()
def client():
    """FastAPI TestClient with the full app."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# 4.2 — Happy path: both headers present → 200
# ---------------------------------------------------------------------------


class TestHappyPath:
    """POST with both Authorization and X-GitHub-Token headers → 200."""

    @patch("backend.api.v1.routes.run_review", return_value=MOCK_REVIEW_RESPONSE)
    def test_returns_200_with_both_headers(self, mock_run, client):
        response = client.post(
            REVIEW_URL,
            json=VALID_BODY,
            headers={
                "Authorization": "Bearer testkey",
                "X-GitHub-Token": "ghtoken",
            },
        )
        assert response.status_code == 200, response.text

    @patch("backend.api.v1.routes.run_review", return_value=MOCK_REVIEW_RESPONSE)
    def test_response_body_is_valid_review_response(self, mock_run, client):
        response = client.post(
            REVIEW_URL,
            json=VALID_BODY,
            headers={
                "Authorization": "Bearer testkey",
                "X-GitHub-Token": "ghtoken",
            },
        )
        data = response.json()
        assert "summary" in data
        assert "approved" in data
        assert "bugs" in data

    @patch("backend.api.v1.routes.run_review", return_value=MOCK_REVIEW_RESPONSE)
    def test_run_review_called_once(self, mock_run, client):
        client.post(
            REVIEW_URL,
            json=VALID_BODY,
            headers={
                "Authorization": "Bearer testkey",
                "X-GitHub-Token": "ghtoken",
            },
        )
        mock_run.assert_called_once_with(ANY, api_key="testkey", github_token="ghtoken")


# ---------------------------------------------------------------------------
# 4.3 — Missing X-GitHub-Token → 422
# ---------------------------------------------------------------------------


class TestMissingGitHubToken:
    """POST without X-GitHub-Token → FastAPI must return 422."""

    def test_missing_x_github_token_returns_422(self, client):
        response = client.post(
            REVIEW_URL,
            json=VALID_BODY,
            headers={"Authorization": "Bearer testkey"},
            # deliberately no X-GitHub-Token
        )
        assert response.status_code == 422, (
            f"Expected 422 when X-GitHub-Token is absent, got {response.status_code}: {response.text}"
        )


# ---------------------------------------------------------------------------
# 4.4 — Missing Authorization → 200 (api_key defaults to empty)
# ---------------------------------------------------------------------------


class TestMissingAuthorization:
    """POST without Authorization header → still 200; api_key defaults to empty (env fallback)."""

    @patch("backend.api.v1.routes.run_review", return_value=MOCK_REVIEW_RESPONSE)
    def test_missing_authorization_returns_200(self, mock_run, client):
        response = client.post(
            REVIEW_URL,
            json=VALID_BODY,
            headers={"X-GitHub-Token": "ghtoken"},
            # deliberately no Authorization
        )
        assert response.status_code == 200, (
            f"Expected 200 when Authorization is absent (api_key optional), "
            f"got {response.status_code}: {response.text}"
        )


# ---------------------------------------------------------------------------
# 4.5 — Body with legacy fields → Pydantic ignores extras, request still passes
# ---------------------------------------------------------------------------


class TestLegacyBodyFields:
    """Body including old api_key/github_token fields → Pydantic ignores them, request passes."""

    @patch("backend.api.v1.routes.run_review", return_value=MOCK_REVIEW_RESPONSE)
    def test_legacy_body_fields_are_ignored(self, mock_run, client):
        legacy_body = {
            **VALID_BODY,
            "api_key": "old-api-key",
            "github_token": "old-github-token",
        }
        response = client.post(
            REVIEW_URL,
            json=legacy_body,
            headers={
                "Authorization": "Bearer testkey",
                "X-GitHub-Token": "ghtoken",
            },
        )
        assert response.status_code == 200, (
            f"Expected 200 even with legacy body fields, got {response.status_code}: {response.text}"
        )
