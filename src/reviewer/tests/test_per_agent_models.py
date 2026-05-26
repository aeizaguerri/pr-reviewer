"""Regression tests: per-role model propagation to Agno agents and Team leader."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.reviewer.models import ReviewContext


@pytest.fixture
def anyio_backend():
    return "asyncio"


class TestPerAgentModels:
    """Ensure each specialist and the Team leader receives its own explicit config."""

    def _make_context(
        self,
        shared_prompt: str = "test prompt",
        impact_result=None,
    ) -> ReviewContext:
        return ReviewContext(
            owner="owner",
            repo="repo",
            pr_number=1,
            head_sha="abc123",
            pr_title="Fix bug",
            diff_text="### file.py\n@@ -1 +1 @@\n-patch",
            changed_paths=["file.py"],
            shared_prompt=shared_prompt,
            impact_result=impact_result,
        )

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.Team")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_team_leader_receives_leader_role_config(
        self, mock_openai_like, mock_team_cls, mock_agent_cls
    ):
        """Regression #2103: Team leader MUST get explicit OpenAILike from leader config."""
        from src.reviewer.orchestrator import _run_bug_reviewers

        ctx = self._make_context()
        role_configs = {
            "bug": ("bug-model", "https://bug.url/v1", "bug-key"),
            "security": ("sec-model", "https://sec.url/v1", "sec-key"),
            "cross_repo": ("cross-model", "https://cross.url/v1", "cross-key"),
            "leader": ("leader-model", "https://leader.url/v1", "leader-key"),
        }

        mock_team = MagicMock()
        mock_team_cls.return_value = mock_team
        mock_msg_a = MagicMock(agent_id="bug-reviewer-a", content=json.dumps({"bugs": []}))
        mock_msg_b = MagicMock(agent_id="bug-reviewer-b", content=json.dumps({"bugs": []}))
        mock_team.run.return_value = MagicMock(member_responses=[mock_msg_a, mock_msg_b])

        await _run_bug_reviewers(ctx, role_configs, supports_structured_output=True)

        # Leader must receive leader-role config explicitly
        leader_model_call = mock_openai_like.call_args_list[-1]
        assert leader_model_call.kwargs == {
            "id": "leader-model",
            "base_url": "https://leader.url/v1",
            "api_key": "leader-key",
        }

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.Team")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_bug_agents_receive_bug_role_config(
        self, mock_openai_like, mock_team_cls, mock_agent_cls
    ):
        """Bug A/B agents MUST use bug-role model, not leader or any fallback."""
        from src.reviewer.orchestrator import _run_bug_reviewers

        ctx = self._make_context()
        role_configs = {
            "bug": ("bug-model", "https://bug.url/v1", "bug-key"),
            "security": ("sec-model", "https://sec.url/v1", "sec-key"),
            "cross_repo": ("cross-model", "https://cross.url/v1", "cross-key"),
            "leader": ("leader-model", "https://leader.url/v1", "leader-key"),
        }

        mock_team = MagicMock()
        mock_team_cls.return_value = mock_team
        mock_msg_a = MagicMock(agent_id="bug-reviewer-a", content=json.dumps({"bugs": []}))
        mock_msg_b = MagicMock(agent_id="bug-reviewer-b", content=json.dumps({"bugs": []}))
        mock_team.run.return_value = MagicMock(member_responses=[mock_msg_a, mock_msg_b])

        await _run_bug_reviewers(ctx, role_configs, supports_structured_output=True)

        # First two OpenAILike calls are for agent_a and agent_b
        bug_calls = mock_openai_like.call_args_list[:2]
        for call in bug_calls:
            assert call.kwargs["id"] == "bug-model"
            assert call.kwargs["base_url"] == "https://bug.url/v1"
            assert call.kwargs["api_key"] == "bug-key"

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_security_reviewer_receives_security_role_config(
        self, mock_openai_like, mock_agent_cls
    ):
        """Security specialist MUST use security-role config."""
        from src.reviewer.orchestrator import _run_security_reviewer

        ctx = self._make_context()
        role_configs = {
            "bug": ("bug-model", "https://bug.url/v1", "bug-key"),
            "security": ("sec-model", "https://sec.url/v1", "sec-key"),
            "cross_repo": ("cross-model", "https://cross.url/v1", "cross-key"),
            "leader": ("leader-model", "https://leader.url/v1", "leader-key"),
        }

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(return_value=MagicMock(content=json.dumps({"bugs": []})))

        await _run_security_reviewer(ctx, role_configs, supports_structured_output=True, timeout=120)

        assert mock_openai_like.call_count == 1
        call = mock_openai_like.call_args
        assert call.kwargs == {
            "id": "sec-model",
            "base_url": "https://sec.url/v1",
            "api_key": "sec-key",
        }

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_cross_repo_reviewer_receives_cross_repo_role_config(
        self, mock_openai_like, mock_agent_cls
    ):
        """Cross-repo specialist MUST use cross-repo-role config."""
        from src.reviewer.orchestrator import _run_cross_repo_reviewer
        from src.knowledge.models import ImpactResult, ImpactWarning

        ctx = self._make_context(
            impact_result=ImpactResult(
                warnings=[
                    ImpactWarning(
                        changed_file="file.py",
                        changed_entity="E",
                        affected_service="svc",
                        affected_repository="repo",
                        relationship_type="CONSUMES",
                        severity="high",
                        description="test",
                    )
                ],
                query_time_ms=1.0,
            )
        )
        role_configs = {
            "bug": ("bug-model", "https://bug.url/v1", "bug-key"),
            "security": ("sec-model", "https://sec.url/v1", "sec-key"),
            "cross_repo": ("cross-model", "https://cross.url/v1", "cross-key"),
            "leader": ("leader-model", "https://leader.url/v1", "leader-key"),
        }

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(
            return_value=MagicMock(content=json.dumps({"impact_warnings": []}))
        )

        await _run_cross_repo_reviewer(ctx, role_configs, supports_structured_output=True, timeout=120)

        assert mock_openai_like.call_count == 1
        call = mock_openai_like.call_args
        assert call.kwargs == {
            "id": "cross-model",
            "base_url": "https://cross.url/v1",
            "api_key": "cross-key",
        }

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_arun_multi_agent_review_passes_role_configs_to_specialists(
        self, mock_cross, mock_sec, mock_bug
    ):
        """The orchestrator fan-out must propagate role_configs to all specialists."""
        from src.reviewer.orchestrator import arun_multi_agent_review
        from src.reviewer.models import (
            SpecialistBugOutput,
            SpecialistSecurityOutput,
            SpecialistImpactOutput,
        )

        mock_bug.return_value = (
            SpecialistBugOutput(bugs=[]),
            SpecialistBugOutput(bugs=[]),
        )
        mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
        mock_cross.return_value = SpecialistImpactOutput(impact_warnings=[])

        role_configs = {
            "bug": ("bug-model", "https://bug.url/v1", "bug-key"),
            "security": ("sec-model", "https://sec.url/v1", "sec-key"),
            "cross_repo": ("cross-model", "https://cross.url/v1", "cross-key"),
            "leader": ("leader-model", "https://leader.url/v1", "leader-key"),
        }

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                await arun_multi_agent_review(
                    "owner", "repo", 1, role_configs=role_configs
                )

        # Mocks receive positional args: (ctx, role_configs, supports_structured_output, ...)
        assert mock_bug.call_args[0][1] == role_configs
        assert mock_sec.call_args[0][1] == role_configs
        assert mock_cross.call_args[0][1] == role_configs
