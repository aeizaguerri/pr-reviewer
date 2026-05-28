"""Unit tests: run_review() delegates to the multi-agent orchestrator."""

from unittest.mock import patch

import pytest

from src.reviewer.models import ReviewOutput, ReviewRequest


class TestRunReview:
    _PROVIDER_CONFIG = ("my-model", "https://api.example.com/v1", "sk-test")

    def _make_output(self, approved: bool = True, bugs=None):
        return ReviewOutput(
            summary="Looks good.",
            bugs=bugs or [],
            approved=approved,
        )

    @patch("src.reviewer.orchestrator.run_multi_agent_review")
    def test_delegates_to_orchestrator(self, mock_orch):
        """run_review must call run_multi_agent_review with request fields."""
        from src.reviewer.agent import run_review

        expected = self._make_output()
        mock_orch.return_value = expected

        request = ReviewRequest(
            owner="owner",
            repo="repo",
            pr_number=1,
            role_configs={
                "bug": self._PROVIDER_CONFIG,
                "security": self._PROVIDER_CONFIG,
                "cross_repo": self._PROVIDER_CONFIG,
            },
            github_token="ghp-tok",
            supports_structured_output=True,
        )
        result = run_review(request)

        mock_orch.assert_called_once()
        kwargs = mock_orch.call_args.kwargs
        assert kwargs["owner"] == "owner"
        assert kwargs["repo"] == "repo"
        assert kwargs["pr_number"] == 1
        assert kwargs["role_configs"]["bug"] == self._PROVIDER_CONFIG
        assert kwargs["github_token"] == "ghp-tok"
        assert kwargs["supports_structured_output"] is True
        assert result == expected

    @patch("src.reviewer.orchestrator.run_multi_agent_review")
    def test_returns_review_output(self, mock_orch):
        """run_review must return a ReviewOutput instance."""
        from src.reviewer.agent import run_review

        expected = self._make_output(approved=True)
        mock_orch.return_value = expected

        request = ReviewRequest(
            owner="o", repo="r", pr_number=2,
            role_configs={"bug": self._PROVIDER_CONFIG, "security": self._PROVIDER_CONFIG, "cross_repo": self._PROVIDER_CONFIG},
        )
        result = run_review(request)

        assert isinstance(result, ReviewOutput)
        assert result.approved is True
        assert result.summary == "Looks good."

    @patch("src.reviewer.orchestrator.run_multi_agent_review")
    def test_uses_default_github_token_and_structured_output(self, mock_orch):
        """Defaults: empty github_token and supports_structured_output=True."""
        from src.reviewer.agent import run_review

        mock_orch.return_value = self._make_output()

        request = ReviewRequest(
            owner="o", repo="r", pr_number=3,
            role_configs={"bug": self._PROVIDER_CONFIG, "security": self._PROVIDER_CONFIG, "cross_repo": self._PROVIDER_CONFIG},
        )
        run_review(request)

        kwargs = mock_orch.call_args.kwargs
        assert kwargs["github_token"] == ""
        assert kwargs["supports_structured_output"] is True

    def test_rejects_stale_leader_role_config(self):
        """run_review must fail fast when role_configs contains 'leader'."""
        from src.reviewer.agent import run_review

        bad_configs = {
            "bug": self._PROVIDER_CONFIG,
            "security": self._PROVIDER_CONFIG,
            "cross_repo": self._PROVIDER_CONFIG,
            "leader": self._PROVIDER_CONFIG,
        }
        request = ReviewRequest(owner="o", repo="r", pr_number=4, role_configs=bad_configs)

        with pytest.raises(ValueError, match="leader"):
            run_review(request)

    def test_rejects_leader_only_role_config(self):
        """Triangulation: leader-only config must also fail fast."""
        from src.reviewer.agent import run_review

        bad_configs = {"leader": self._PROVIDER_CONFIG}
        request = ReviewRequest(owner="o", repo="r", pr_number=5, role_configs=bad_configs)

        with pytest.raises(ValueError, match="leader"):
            run_review(request)


class TestLegacyEntrypointRemoved:
    """Verify review_pr_with_config is not a supported public entrypoint."""

    def test_review_pr_with_config_is_not_exported(self):
        from src.reviewer import agent

        assert not hasattr(agent, "review_pr_with_config")

    def test_review_pr_with_config_cannot_be_imported(self):
        import importlib

        with pytest.raises(AttributeError):
            mod = importlib.import_module("src.reviewer.agent")
            getattr(mod, "review_pr_with_config")
