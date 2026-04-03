"""Unit tests: review_pr_with_config() calls _build_agent_with_config() with injected config."""

from unittest.mock import MagicMock, patch

import pytest

from src.reviewer.models import ReviewOutput


# ---------------------------------------------------------------------------
# review_pr_with_config — config injection
# ---------------------------------------------------------------------------


class TestReviewPrWithConfig:
    _PROVIDER_CONFIG = ("my-model", "https://api.example.com/v1", "sk-test")

    def _make_review_output(self, approved: bool = True, bugs=None):
        return ReviewOutput(
            summary="Looks good.",
            bugs=bugs or [],
            approved=approved,
        )

    @patch("src.reviewer.agent.post_review_comments")
    @patch("src.reviewer.agent.fetch_pr_data")
    @patch("src.reviewer.agent._build_agent_with_config")
    def test_calls_build_agent_with_injected_config(self, mock_build, mock_fetch, mock_post):
        from src.reviewer.agent import review_pr_with_config

        mock_fetch.return_value = ("diff text", "abc123", "Fix: something")
        mock_run = MagicMock()
        mock_run.content = self._make_review_output()
        mock_build.return_value.run.return_value = mock_run

        review_pr_with_config("owner", "repo", 1, self._PROVIDER_CONFIG, github_token="ghp-tok")

        mock_build.assert_called_once_with(
            self._PROVIDER_CONFIG, supports_structured_output=True, debug=False
        )

    @patch("src.reviewer.agent.post_review_comments")
    @patch("src.reviewer.agent.fetch_pr_data")
    @patch("src.reviewer.agent._build_agent_with_config")
    def test_passes_github_token_to_fetch_pr_data(self, mock_build, mock_fetch, mock_post):
        from src.reviewer.agent import review_pr_with_config

        mock_fetch.return_value = ("diff", "sha", "title")
        mock_run = MagicMock()
        mock_run.content = self._make_review_output()
        mock_build.return_value.run.return_value = mock_run

        review_pr_with_config("owner", "repo", 1, self._PROVIDER_CONFIG, github_token="ghp-tok")

        mock_fetch.assert_called_once_with("owner", "repo", 1, github_token="ghp-tok")

    @patch("src.reviewer.agent.post_review_comments")
    @patch("src.reviewer.agent.fetch_pr_data")
    @patch("src.reviewer.agent._build_agent_with_config")
    def test_returns_review_output(self, mock_build, mock_fetch, mock_post):
        from src.reviewer.agent import review_pr_with_config

        mock_fetch.return_value = ("diff", "sha", "title")
        expected = self._make_review_output(approved=True)
        mock_run = MagicMock()
        mock_run.content = expected
        mock_build.return_value.run.return_value = mock_run

        result = review_pr_with_config("owner", "repo", 1, self._PROVIDER_CONFIG)

        assert result == expected
        assert result.approved is True

    @patch("src.reviewer.agent.post_review_comments")
    @patch("src.reviewer.agent.fetch_pr_data")
    @patch("src.reviewer.agent._build_agent_with_config")
    def test_does_not_post_comments_when_no_bugs(self, mock_build, mock_fetch, mock_post):
        from src.reviewer.agent import review_pr_with_config

        mock_fetch.return_value = ("diff", "sha", "title")
        mock_run = MagicMock()
        mock_run.content = self._make_review_output(bugs=[])
        mock_build.return_value.run.return_value = mock_run

        review_pr_with_config("owner", "repo", 1, self._PROVIDER_CONFIG)

        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# Backward compatibility: review_pr() is unchanged
# ---------------------------------------------------------------------------


class TestReviewPrBackwardCompat:
    def test_review_pr_signature_unchanged(self):
        """review_pr() must still accept (owner, repo, pr_number) — no new required params."""
        import inspect
        from src.reviewer.agent import review_pr

        sig = inspect.signature(review_pr)
        params = list(sig.parameters.keys())
        assert params == ["owner", "repo", "pr_number"], f"review_pr() signature changed: {params}"
