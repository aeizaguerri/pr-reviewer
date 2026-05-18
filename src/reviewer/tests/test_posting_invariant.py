"""RED-phase tests: exactly-once posting invariant (task 3.4)."""

from unittest.mock import patch

import pytest

from src.reviewer.models import (
    BugReport,
    ReviewContext,
    SpecialistBugOutput,
    SpecialistImpactOutput,
    SpecialistSecurityOutput,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


class TestPostingInvariant:
    _PROVIDER_CONFIG = ("my-model", "https://api.example.com/v1", "sk-test")

    def _make_context(self) -> ReviewContext:
        return ReviewContext(
            owner="owner",
            repo="repo",
            pr_number=1,
            head_sha="abc123",
            pr_title="Fix bug",
            diff_text="### file.py\n@@ -1 +1 @@\n-patch",
            changed_paths=["file.py"],
            shared_prompt="test prompt",
        )

    def _make_bug(self) -> BugReport:
        return BugReport(
            file="src/a.py",
            line=10,
            severity="major",
            description="bug",
            suggestion="fix",
        )

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.post_review_comments")
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_posting_called_once_with_bugs(self, mock_cross, mock_sec, mock_bug, mock_post):
        """Task 3.4: post_review_comments called exactly once when bugs exist."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        mock_bug.return_value = (
            SpecialistBugOutput(bugs=[self._make_bug()]),
            SpecialistBugOutput(bugs=[]),
        )
        mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
        mock_cross.return_value = SpecialistImpactOutput(impact_warnings=[])
        mock_post.return_value = "posted"

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                await arun_multi_agent_review(
                    "owner", "repo", 1, self._PROVIDER_CONFIG, github_token="tok"
                )

        mock_post.assert_called_once()

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.post_review_comments")
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_posting_not_called_when_no_bugs(self, mock_cross, mock_sec, mock_bug, mock_post):
        """Task 3.4: post_review_comments not called when result.bugs is empty."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        mock_bug.return_value = (
            SpecialistBugOutput(bugs=[]),
            SpecialistBugOutput(bugs=[]),
        )
        mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
        mock_cross.return_value = SpecialistImpactOutput(impact_warnings=[])

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                await arun_multi_agent_review("owner", "repo", 1, self._PROVIDER_CONFIG)

        mock_post.assert_not_called()

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_no_specialist_has_posting_tools(self, mock_cross, mock_sec, mock_bug):
        """Task 3.4: specialist agents do not receive github_token or posting tools."""
        from src.reviewer.orchestrator import _build_agent

        agent = _build_agent(
            agent_id="test",
            instructions="test",
            provider_config=self._PROVIDER_CONFIG,
            output_schema=None,
        )
        assert agent.tools is None or len(agent.tools) == 0
