"""RED-phase tests: multi-agent routing seam (tasks 1.1, 1.9)."""

from unittest.mock import patch


from src.reviewer.models import ReviewOutput


class TestMultiAgentRouting:
    _PROVIDER_CONFIG = ("my-model", "https://api.example.com/v1", "sk-test")

    def _make_output(self) -> ReviewOutput:
        return ReviewOutput(summary="test", approved=True, bugs=[], impact_warnings=[])

    @patch("src.reviewer.orchestrator.run_multi_agent_review")
    def test_review_pr_with_config_calls_orchestrator_not_build_agent(self, mock_orch):
        """Task 1.1 RED: review_pr_with_config must delegate to run_multi_agent_review
        and must NOT call the legacy mono-agent _build_agent_with_config path."""
        mock_orch.return_value = self._make_output()
        from src.reviewer.agent import review_pr_with_config

        with patch("src.reviewer.agent._build_agent_with_config") as mock_build:
            result = review_pr_with_config("owner", "repo", 1, self._PROVIDER_CONFIG)

            mock_orch.assert_called_once()
            mock_build.assert_not_called()
            assert isinstance(result, ReviewOutput)

    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    @patch("src.reviewer.orchestrator.fetch_pr_data")
    def test_run_multi_agent_review_completes_successfully(
        self, mock_fetch, mock_cross, mock_sec, mock_bug
    ):
        """Task 1.9/3.7: orchestrator now runs full multi-agent pipeline."""
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
    def test_review_pr_with_config_returns_review_output_shape(self, mock_orch):
        """Task 1.9 RED: even when the orchestrator is stubbed, if we patch the
        orchestrator entry we must receive a valid ReviewOutput shape."""
        expected = self._make_output()
        mock_orch.return_value = expected
        from src.reviewer.agent import review_pr_with_config

        result = review_pr_with_config("owner", "repo", 1, self._PROVIDER_CONFIG)

        assert isinstance(result, ReviewOutput)
        assert result.summary == expected.summary
        assert result.approved == expected.approved
