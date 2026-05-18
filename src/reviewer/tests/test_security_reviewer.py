"""RED-phase tests: Security Reviewer runner (tasks 2.3, 2.4)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.reviewer.models import (
    BugReport,
    ReviewContext,
    SpecialistFailure,
    SpecialistSecurityOutput,
)




@pytest.fixture
def anyio_backend():
    return "asyncio"

class TestSecurityReviewer:
    _PROVIDER_CONFIG = ("my-model", "https://api.example.com/v1", "sk-test")

    def _make_context(self, shared_prompt: str = "test prompt") -> ReviewContext:
        return ReviewContext(
            owner="owner",
            repo="repo",
            pr_number=1,
            head_sha="abc123",
            pr_title="Fix bug",
            diff_text="### file.py\n@@ -1 +1 @@\n-patch",
            changed_paths=["file.py"],
            shared_prompt=shared_prompt,
        )

    def _make_bug_report(self, file: str = "src/a.py", line: int = 10) -> BugReport:
        return BugReport(
            file=file,
            line=line,
            severity="critical",
            description="SQL injection vulnerability",
            suggestion="Use parameterized queries",
        )

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_agent_created_without_github_token_or_posting(
        self, mock_openai_like, mock_agent_cls
    ):
        """Task 2.3 RED: Security agent has no github_token or posting tools."""
        from src.reviewer.orchestrator import _run_security_reviewer

        ctx = self._make_context()

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(return_value=MagicMock(content=json.dumps({"bugs": []})))

        await _run_security_reviewer(
            ctx, self._PROVIDER_CONFIG, supports_structured_output=True, timeout=120
        )

        call = mock_agent_cls.call_args
        assert "github_token" not in str(call)
        assert "post_review_comments" not in str(call)
        assert call.kwargs.get("tools") is None

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_receives_security_instructions_and_shared_prompt(
        self, mock_openai_like, mock_agent_cls
    ):
        """Task 2.3 RED: Security reviewer gets SECURITY_REVIEWER_INSTRUCTIONS + shared prompt."""
        from src.reviewer.orchestrator import _run_security_reviewer

        shared_prompt = "security test prompt"
        ctx = self._make_context(shared_prompt=shared_prompt)

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(return_value=MagicMock(content=json.dumps({"bugs": []})))

        await _run_security_reviewer(
            ctx, self._PROVIDER_CONFIG, supports_structured_output=True, timeout=120
        )

        # Verify agent was created with security instructions
        call = mock_agent_cls.call_args
        assert "security" in call.kwargs["instructions"].lower()

        # Verify arun was called with the shared prompt
        mock_agent.arun.assert_called_once()
        assert mock_agent.arun.call_args[0][0] == shared_prompt

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_parse_success_returns_specialist_output(self, mock_openai_like, mock_agent_cls):
        """Task 2.4 GREEN: successful parse returns SpecialistSecurityOutput."""
        from src.reviewer.orchestrator import _run_security_reviewer

        ctx = self._make_context()
        bug = self._make_bug_report()

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(
            return_value=MagicMock(content=json.dumps({"bugs": [bug.model_dump()]}))
        )

        result = await _run_security_reviewer(
            ctx, self._PROVIDER_CONFIG, supports_structured_output=True, timeout=120
        )

        assert isinstance(result, SpecialistSecurityOutput)
        assert len(result.bugs) == 1
        assert result.bugs[0].file == bug.file
        assert result.bugs[0].severity == "critical"

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_parse_failure_returns_specialist_failure(self, mock_openai_like, mock_agent_cls):
        """Task 2.4 GREEN: parse failure returns SpecialistFailure with role."""
        from src.reviewer.orchestrator import _run_security_reviewer

        ctx = self._make_context()

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(return_value=MagicMock(content="not valid json"))

        result = await _run_security_reviewer(
            ctx, self._PROVIDER_CONFIG, supports_structured_output=True, timeout=120
        )

        assert isinstance(result, SpecialistFailure)
        assert result.role == "security-reviewer"

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_timeout_returns_specialist_failure(self, mock_openai_like, mock_agent_cls):
        """Task 2.4 GREEN: timeout returns SpecialistFailure with reason."""
        import asyncio

        from src.reviewer.orchestrator import _run_security_reviewer

        ctx = self._make_context()

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        async def slow_run(*args, **kwargs):
            await asyncio.sleep(10)
            return MagicMock(content=json.dumps({"bugs": []}))

        mock_agent.arun = slow_run

        result = await _run_security_reviewer(
            ctx, self._PROVIDER_CONFIG, supports_structured_output=True, timeout=0.1
        )

        assert isinstance(result, SpecialistFailure)
        assert result.role == "security-reviewer"
        assert "timeout" in result.reason.lower()
