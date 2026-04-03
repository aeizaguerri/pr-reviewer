"""Unit tests: L1 — Author association gating in the GitHub webhook handler."""

import hashlib
import hmac
import importlib
import json
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_payload(author_association: str | None = "OWNER") -> dict:
    """Build a minimal webhook payload for a PR opened event."""
    pr = {"number": 42}
    if author_association is not None:
        pr["author_association"] = author_association

    return {
        "action": "opened",
        "pull_request": pr,
        "repository": {"full_name": "myorg/myrepo"},
    }


def _sign_body(body: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


# ---------------------------------------------------------------------------
# Fixture: a TestClient pre-configured with the secret
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch):
    """Return a TestClient with GITHUB_WEBHOOK_SECRET set."""
    secret = "test-secret"
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)

    # Reload backend.main so WEBHOOK_SECRET picks up the env var
    import backend.main as main_module

    importlib.reload(main_module)

    from starlette.testclient import TestClient

    yield TestClient(main_module.app, raise_server_exceptions=True), secret, main_module


def _post(client_tuple, payload: dict):
    client, secret, _ = client_tuple
    body = json.dumps(payload).encode()
    sig = _sign_body(body, secret)
    return client.post(
        "/api/v1/webhook/github",
        content=body,
        headers={"Content-Type": "application/json", "x-hub-signature-256": sig},
    )


# ---------------------------------------------------------------------------
# Tests — SC-L1-1 through SC-L1-6
# ---------------------------------------------------------------------------


class TestAuthorAssociationGating:
    def test_trusted_owner_triggers_review(self, client):
        """SC-L1-1: OWNER association → review_pr() is called."""
        _, _, main_module = client
        mock_result = MagicMock(approved=True, bugs=[], summary="ok")
        with patch.object(
            main_module, "review_pr", return_value=mock_result
        ) as mock_review:
            resp = _post(client, _make_payload("OWNER"))

        assert resp.status_code == 202
        assert resp.json()["status"] == "reviewed"
        mock_review.assert_called_once()

    def test_trusted_member_triggers_review(self, client):
        """SC-L1-1 (MEMBER): MEMBER association → review_pr() is called."""
        _, _, main_module = client
        mock_result = MagicMock(approved=True, bugs=[], summary="ok")
        with patch.object(
            main_module, "review_pr", return_value=mock_result
        ) as mock_review:
            resp = _post(client, _make_payload("MEMBER"))

        assert resp.status_code == 202
        assert resp.json()["status"] == "reviewed"
        mock_review.assert_called_once()

    def test_trusted_collaborator_triggers_review(self, client):
        """SC-L1-1 (COLLABORATOR): COLLABORATOR association → review_pr() is called."""
        _, _, main_module = client
        mock_result = MagicMock(approved=True, bugs=[], summary="ok")
        with patch.object(
            main_module, "review_pr", return_value=mock_result
        ) as mock_review:
            resp = _post(client, _make_payload("COLLABORATOR"))

        assert resp.status_code == 202
        assert resp.json()["status"] == "reviewed"
        mock_review.assert_called_once()

    def test_none_association_skips_review(self, client):
        """SC-L1-2: NONE association → skipped, review_pr() NOT called."""
        _, _, main_module = client
        with patch.object(main_module, "review_pr") as mock_review:
            resp = _post(client, _make_payload("NONE"))

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "skipped"
        assert "untrusted" in data["reason"]
        mock_review.assert_not_called()

    def test_first_timer_skips_review(self, client):
        """SC-L1-3: FIRST_TIMER → skipped."""
        _, _, main_module = client
        with patch.object(main_module, "review_pr") as mock_review:
            resp = _post(client, _make_payload("FIRST_TIMER"))

        assert resp.status_code == 202
        assert resp.json()["status"] == "skipped"
        mock_review.assert_not_called()

    def test_first_time_contributor_skips_review(self, client):
        """SC-L1-4: FIRST_TIME_CONTRIBUTOR → skipped."""
        _, _, main_module = client
        with patch.object(main_module, "review_pr") as mock_review:
            resp = _post(client, _make_payload("FIRST_TIME_CONTRIBUTOR"))

        assert resp.status_code == 202
        assert resp.json()["status"] == "skipped"
        mock_review.assert_not_called()

    def test_missing_author_association_defaults_to_skip(self, client):
        """SC-L1-6: Missing author_association → defaults to NONE → skipped."""
        _, _, main_module = client
        with patch.object(main_module, "review_pr") as mock_review:
            resp = _post(client, _make_payload(None))

        assert resp.status_code == 202
        assert resp.json()["status"] == "skipped"
        mock_review.assert_not_called()

    def test_null_author_association_is_skipped(self, client):
        """C3: Explicit null author_association in JSON → skipped, no crash."""
        _, _, main_module = client
        # Build payload with explicit null value (not missing key)
        payload = {
            "action": "opened",
            "pull_request": {"number": 42, "author_association": None},
            "repository": {"full_name": "myorg/myrepo"},
        }
        with patch.object(main_module, "review_pr") as mock_review:
            resp = _post(client, payload)

        assert resp.status_code == 202
        assert resp.json()["status"] == "skipped"
        mock_review.assert_not_called()

    def test_contributor_blocked_with_default_config(self, client):
        """W1: CONTRIBUTOR is NOT in default trusted list → skipped."""
        _, _, main_module = client
        with patch.object(main_module, "review_pr") as mock_review:
            resp = _post(client, _make_payload("CONTRIBUTOR"))

        assert resp.status_code == 202
        assert resp.json()["status"] == "skipped"
        mock_review.assert_not_called()

    def test_empty_trusted_list_falls_back_to_default(self, client, monkeypatch):
        """W2: Empty TRUSTED_AUTHOR_ASSOCIATIONS → falls back to default, OWNER still trusted."""
        _, _, main_module = client
        import src.core.config as cfg_module

        monkeypatch.setattr(cfg_module.Config, "TRUSTED_AUTHOR_ASSOCIATIONS", "")

        mock_result = MagicMock(approved=True, bugs=[], summary="ok")
        with patch.object(
            main_module, "review_pr", return_value=mock_result
        ) as mock_review:
            resp = _post(client, _make_payload("OWNER"))

        assert resp.status_code == 202
        assert resp.json()["status"] == "reviewed"
        mock_review.assert_called_once()

    def test_lowercase_trusted_list_matches_uppercase_association(
        self, client, monkeypatch
    ):
        """Case-insensitivity: lowercase env var values must match GitHub's uppercase values."""
        _, _, main_module = client
        import src.core.config as cfg_module

        monkeypatch.setattr(
            cfg_module.Config,
            "TRUSTED_AUTHOR_ASSOCIATIONS",
            "owner,member,collaborator",
        )

        mock_result = MagicMock(approved=True, bugs=[], summary="ok")
        with patch.object(
            main_module, "review_pr", return_value=mock_result
        ) as mock_review:
            resp = _post(client, _make_payload("OWNER"))

        assert resp.status_code == 202
        assert resp.json()["status"] == "reviewed"
        mock_review.assert_called_once()

    def test_custom_trusted_list_restricts_contributor(self, client, monkeypatch):
        """SC-L1-5: Custom TRUSTED_AUTHOR_ASSOCIATIONS env var — CONTRIBUTOR excluded."""
        _, _, main_module = client
        import src.core.config as cfg_module

        monkeypatch.setattr(
            cfg_module.Config, "TRUSTED_AUTHOR_ASSOCIATIONS", "OWNER,MEMBER"
        )

        with patch.object(main_module, "review_pr") as mock_review:
            resp = _post(client, _make_payload("CONTRIBUTOR"))

        assert resp.status_code == 202
        assert resp.json()["status"] == "skipped"
        mock_review.assert_not_called()

    def test_custom_trusted_list_allows_owner(self, client, monkeypatch):
        """SC-L1-5 (OWNER still trusted): Custom list OWNER,MEMBER — OWNER still passes."""
        _, _, main_module = client
        import src.core.config as cfg_module

        monkeypatch.setattr(
            cfg_module.Config, "TRUSTED_AUTHOR_ASSOCIATIONS", "OWNER,MEMBER"
        )

        mock_result = MagicMock(approved=True, bugs=[], summary="ok")
        with patch.object(
            main_module, "review_pr", return_value=mock_result
        ) as mock_review:
            resp = _post(client, _make_payload("OWNER"))

        assert resp.status_code == 202
        assert resp.json()["status"] == "reviewed"
        mock_review.assert_called_once()
