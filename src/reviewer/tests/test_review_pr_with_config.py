"""Unit tests: review_pr_with_config() delegates to the multi-agent orchestrator."""

from unittest.mock import patch


from src.reviewer.models import ReviewOutput


class TestReviewPrWithConfig:
    _PROVIDER_CONFIG = ("my-model", "https://api.example.com/v1", "sk-test")

    def _make_output(self, approved: bool = True, bugs=None):
        return ReviewOutput(
            summary="Looks good.",
            bugs=bugs or [],
            approved=approved,
        )

    @patch("src.reviewer.orchestrator.run_multi_agent_review")
    def test_delegates_to_orchestrator(self, mock_orch):
        """Task 1.1/1.9: review_pr_with_config must call run_multi_agent_review."""
        from src.reviewer.agent import review_pr_with_config

        expected = self._make_output()
        mock_orch.return_value = expected

        result = review_pr_with_config(
            "owner", "repo", 1, self._PROVIDER_CONFIG, github_token="ghp-tok"
        )

        mock_orch.assert_called_once()
        assert result == expected

    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    @patch("src.reviewer.orchestrator.fetch_pr_data")
    def test_full_pipeline_runs(self, mock_fetch, mock_cross, mock_sec, mock_bug):
        """Task 1.9/3.7: full multi-agent pipeline completes without exceptions."""
        from src.reviewer.agent import review_pr_with_config
        from src.reviewer.models import (
            SpecialistBugOutput,
            SpecialistSecurityOutput,
            SpecialistImpactOutput,
        )

        mock_fetch.return_value = ("diff", "sha", "title")
        mock_bug.return_value = (
            SpecialistBugOutput(bugs=[]),
            SpecialistBugOutput(bugs=[]),
        )
        mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
        mock_cross.return_value = SpecialistImpactOutput(impact_warnings=[])

        result = review_pr_with_config("owner", "repo", 1, self._PROVIDER_CONFIG)
        assert isinstance(result, ReviewOutput)

    @patch("src.reviewer.orchestrator.run_multi_agent_review")
    def test_returns_review_output(self, mock_orch):
        """Task 1.9: shape compatibility — must return ReviewOutput."""
        from src.reviewer.agent import review_pr_with_config

        expected = self._make_output(approved=True)
        mock_orch.return_value = expected

        result = review_pr_with_config("owner", "repo", 1, self._PROVIDER_CONFIG)

        assert isinstance(result, ReviewOutput)
        assert result.approved is True

    @patch("src.reviewer.orchestrator.post_review_comments")
    @patch("src.reviewer.orchestrator.run_multi_agent_review")
    def test_does_not_post_comments_when_no_bugs(self, mock_orch, mock_post):
        """Task 1.9: when orchestrator returns no bugs, no posting occurs."""
        from src.reviewer.agent import review_pr_with_config

        expected = self._make_output(bugs=[])
        mock_orch.return_value = expected

        review_pr_with_config("owner", "repo", 1, self._PROVIDER_CONFIG)

        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# Backward compatibility: review_pr() signature is unchanged
# ---------------------------------------------------------------------------


class TestReviewPrBackwardCompat:
    def test_review_pr_signature_unchanged(self):
        """review_pr() must still accept (owner, repo, pr_number) — no new required params."""
        import inspect
        from src.reviewer.agent import review_pr

        sig = inspect.signature(review_pr)
        params = list(sig.parameters.keys())
        assert params == ["owner", "repo", "pr_number"], f"review_pr() signature changed: {params}"


class TestReviewPrDefaultProvider:
    @patch("src.reviewer.agent.Config.get_model_config")
    @patch("src.reviewer.orchestrator.run_multi_agent_review")
    def test_cerebras_default_provider_keeps_structured_output(self, mock_orch, mock_get_model_config):
        from src.reviewer.agent import review_pr
        from src.reviewer.models import ReviewOutput

        mock_get_model_config.return_value = (
            "meta-llama/Llama-3.1-8B-Instruct:cerebras",
            "https://router.huggingface.co/v1",
            "hf-key",
        )
        mock_orch.return_value = ReviewOutput(
            summary="ok", approved=True, bugs=[], impact_warnings=[]
        )

        with patch("src.reviewer.agent.Config.DEFAULT_PROVIDER", "cerebras"):
            review_pr("owner", "repo", 1)

        assert mock_orch.call_args.kwargs["supports_structured_output"] is True
