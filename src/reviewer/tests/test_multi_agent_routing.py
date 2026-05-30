"""RED-phase tests: multi-agent routing seam via run_review()."""

from unittest.mock import patch

from src.reviewer.models import ReviewOutput, ReviewRequest


class TestMultiAgentRouting:
    _PROVIDER_CONFIG = ("my-model", "https://api.example.com/v1", "sk-test")

    def _make_output(self) -> ReviewOutput:
        return ReviewOutput(summary="test", approved=True, bugs=[], impact_warnings=[])

    @patch("src.reviewer.orchestrator.run_multi_agent_review")
    def test_run_review_calls_orchestrator(self, mock_orch):
        """run_review must delegate to run_multi_agent_review."""
        mock_orch.return_value = self._make_output()
        from src.reviewer.agent import run_review

        request = ReviewRequest(
            owner="owner",
            repo="repo",
            pr_number=1,
            role_configs={
                "bug": self._PROVIDER_CONFIG,
                "security": self._PROVIDER_CONFIG,
                "cross_repo": self._PROVIDER_CONFIG,
            },
        )
        result = run_review(request)

        mock_orch.assert_called_once()
        assert isinstance(result, ReviewOutput)

    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    @patch("src.reviewer.orchestrator.fetch_pr_data")
    def test_run_multi_agent_review_completes_successfully(
        self, mock_fetch, mock_cross, mock_sec, mock_bug
    ):
        """Orchestrator runs full multi-agent pipeline through run_review."""
        from src.reviewer.agent import run_review
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

        request = ReviewRequest(
            owner="owner",
            repo="repo",
            pr_number=1,
            role_configs={
                "bug": self._PROVIDER_CONFIG,
                "security": self._PROVIDER_CONFIG,
                "cross_repo": self._PROVIDER_CONFIG,
            },
        )
        result = run_review(request)
        assert isinstance(result, ReviewOutput)

    @patch("src.reviewer.orchestrator.run_multi_agent_review")
    def test_run_review_returns_review_output_shape(self, mock_orch):
        """run_review must return a valid ReviewOutput shape."""
        expected = self._make_output()
        mock_orch.return_value = expected
        from src.reviewer.agent import run_review

        request = ReviewRequest(
            owner="owner",
            repo="repo",
            pr_number=1,
            role_configs={
                "bug": self._PROVIDER_CONFIG,
                "security": self._PROVIDER_CONFIG,
                "cross_repo": self._PROVIDER_CONFIG,
            },
        )
        result = run_review(request)

        assert isinstance(result, ReviewOutput)
        assert result.summary == expected.summary
        assert result.approved == expected.approved
