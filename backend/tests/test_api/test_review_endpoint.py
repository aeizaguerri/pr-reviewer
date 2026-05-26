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
    review_health=None,
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
# 4.4 — Missing Authorization → 422 (api_key is required)
# ---------------------------------------------------------------------------


class TestMissingAuthorization:
    """POST without Authorization header → FastAPI must return 422."""

    def test_missing_authorization_returns_422(self, client):
        response = client.post(
            REVIEW_URL,
            json=VALID_BODY,
            headers={"X-GitHub-Token": "ghtoken"},
            # deliberately no Authorization
        )
        assert response.status_code == 422, (
            f"Expected 422 when Authorization is absent (api_key required), "
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


# ---------------------------------------------------------------------------
# 4.6 — Body without provider/model/base_url fields → 200 (public HF path)
# ---------------------------------------------------------------------------


class TestMinimalBodyFields:
    """Body omitting provider/model/base_url → public HF path still succeeds."""

    @patch("backend.api.v1.routes.run_review", return_value=MOCK_REVIEW_RESPONSE)
    def test_request_without_provider_model_fields_returns_200(self, mock_run, client):
        minimal_body = {
            "owner": "o",
            "repo": "r",
            "pr_number": 1,
        }
        response = client.post(
            REVIEW_URL,
            json=minimal_body,
            headers={
                "Authorization": "Bearer testkey",
                "X-GitHub-Token": "ghtoken",
            },
        )
        assert response.status_code == 200, (
            f"Expected 200 for minimal body, got {response.status_code}: {response.text}"
        )

    @patch("backend.api.v1.routes.run_review")
    def test_hf_key_from_authorization_header_is_used_for_agents(self, mock_run, client):
        mock_run.return_value = MOCK_REVIEW_RESPONSE
        minimal_body = {
            "owner": "o",
            "repo": "r",
            "pr_number": 1,
        }
        client.post(
            REVIEW_URL,
            json=minimal_body,
            headers={
                "Authorization": "Bearer user-hf-key",
                "X-GitHub-Token": "ghtoken",
            },
        )
        mock_run.assert_called_once_with(ANY, api_key="user-hf-key", github_token="ghtoken")


# ---------------------------------------------------------------------------
# 3.1 — BugReportResponse includes category and source
# ---------------------------------------------------------------------------


class TestBugReportSchema:
    @patch("backend.api.v1.routes.run_review")
    def test_bug_report_response_has_category_and_source(self, mock_run, client):
        from backend.models.schemas import BugReportResponse

        mock_run.return_value = ReviewResponse(
            summary="test",
            approved=False,
            bugs=[
                BugReportResponse(
                    file="src/a.py",
                    line=10,
                    severity="major",
                    description="bug",
                    suggestion="fix",
                    category="security",
                    source="security-reviewer",
                )
            ],
            impact_warnings=[],
            review_health=None,
        )
        response = client.post(
            REVIEW_URL,
            json=VALID_BODY,
            headers={
                "Authorization": "Bearer testkey",
                "X-GitHub-Token": "ghtoken",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["bugs"]) == 1
        assert data["bugs"][0]["category"] == "security"
        assert data["bugs"][0]["source"] == "security-reviewer"


# ---------------------------------------------------------------------------
# 3.3 — ImpactWarningResponse includes full structured fields
# ---------------------------------------------------------------------------


class TestImpactWarningSchema:
    @patch("backend.api.v1.routes.run_review")
    def test_impact_warning_response_has_full_fields(self, mock_run, client):
        from backend.models.schemas import ImpactWarningResponse

        mock_run.return_value = ReviewResponse(
            summary="test",
            approved=False,
            bugs=[],
            impact_warnings=[
                ImpactWarningResponse(
                    severity="high",
                    description="breaks downstream",
                    changed_file="src/a.py",
                    changed_entity="OrderCreated",
                    affected_service="payment-worker",
                    affected_repository="payment-service",
                    relationship_type="CONSUMES",
                )
            ],
            review_health=None,
        )
        response = client.post(
            REVIEW_URL,
            json=VALID_BODY,
            headers={
                "Authorization": "Bearer testkey",
                "X-GitHub-Token": "ghtoken",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["impact_warnings"]) == 1
        warning = data["impact_warnings"][0]
        assert warning["changed_file"] == "src/a.py"
        assert warning["changed_entity"] == "OrderCreated"
        assert warning["affected_service"] == "payment-worker"
        assert warning["affected_repository"] == "payment-service"
        assert warning["relationship_type"] == "CONSUMES"


# ---------------------------------------------------------------------------
# 3.5 — ReviewHealthResponse optional and serialized
# ---------------------------------------------------------------------------


class TestReviewHealthSchema:
    @patch("backend.api.v1.routes.run_review")
    def test_review_health_response_optional_and_serialized(self, mock_run, client):
        from backend.models.schemas import ReviewHealthResponse

        mock_run.return_value = ReviewResponse(
            summary="test",
            approved=True,
            bugs=[],
            impact_warnings=[],
            review_health=ReviewHealthResponse(
                status="partial",
                warnings=["cross-repo impact reviewer skipped (no graph evidence)."],
            ),
        )
        response = client.post(
            REVIEW_URL,
            json=VALID_BODY,
            headers={
                "Authorization": "Bearer testkey",
                "X-GitHub-Token": "ghtoken",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["review_health"] is not None
        assert data["review_health"]["status"] == "partial"
        assert data["review_health"]["warnings"] == ["cross-repo impact reviewer skipped (no graph evidence)."]
