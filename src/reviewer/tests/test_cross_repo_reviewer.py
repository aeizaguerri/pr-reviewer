"""RED-phase tests: Cross-Repo Impact Reviewer runner (tasks 2.5, 2.6)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.knowledge.models import ImpactResult, ImpactWarning
from src.reviewer.models import ReviewContext, SpecialistFailure, SpecialistImpactOutput


@pytest.fixture
def anyio_backend():
    return "asyncio"


class TestCrossRepoReviewer:
    _PROVIDER_CONFIG = ("my-model", "https://api.example.com/v1", "sk-test")
    _ROLE_CONFIGS = {
        "bug": _PROVIDER_CONFIG,
        "security": _PROVIDER_CONFIG,
        "cross_repo": _PROVIDER_CONFIG,
        "leader": _PROVIDER_CONFIG,
    }

    def _make_context(
        self,
        shared_prompt: str = "test prompt",
        impact_result: ImpactResult | None = None,
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

    def _make_impact_result(self) -> ImpactResult:
        return ImpactResult(
            warnings=[
                ImpactWarning(
                    changed_file="src/contracts/order.py",
                    changed_entity="OrderCreated",
                    affected_service="payment-worker",
                    affected_repository="payment-service",
                    relationship_type="CONSUMES",
                    severity="high",
                    description="Payment worker consumes this contract.",
                )
            ],
            query_time_ms=12.5,
        )

    @pytest.mark.anyio
    async def test_short_circuits_when_no_graph_evidence(self):
        """Task 2.5 RED: when impact_result is None, returns empty output immediately."""
        from src.reviewer.orchestrator import _run_cross_repo_reviewer

        ctx = self._make_context(impact_result=None)

        result = await _run_cross_repo_reviewer(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True, timeout=120
        )

        assert isinstance(result, SpecialistImpactOutput)
        assert len(result.impact_warnings) == 0
        assert result.raw_content == ""

    @pytest.mark.anyio
    async def test_short_circuits_when_empty_warnings(self):
        """Task 2.5 RED: when impact_result has no warnings, returns empty output."""
        from src.reviewer.orchestrator import _run_cross_repo_reviewer

        ctx = self._make_context(impact_result=ImpactResult(warnings=[], query_time_ms=0))

        result = await _run_cross_repo_reviewer(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True, timeout=120
        )

        assert isinstance(result, SpecialistImpactOutput)
        assert len(result.impact_warnings) == 0
        assert result.raw_content == ""

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_agent_created_without_github_token_or_posting(
        self, mock_openai_like, mock_agent_cls
    ):
        """Task 2.5 RED: Cross-repo agent has no github_token or posting tools."""
        from src.reviewer.orchestrator import _run_cross_repo_reviewer

        ctx = self._make_context(impact_result=self._make_impact_result())

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(
            return_value=MagicMock(content=json.dumps({"impact_warnings": []}))
        )

        await _run_cross_repo_reviewer(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True, timeout=120
        )

        call = mock_agent_cls.call_args
        assert "github_token" not in str(call)
        assert "post_review_comments" not in str(call)
        assert call.kwargs.get("tools") is None

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_parse_success_returns_specialist_output(self, mock_openai_like, mock_agent_cls):
        """Task 2.6 GREEN: successful parse returns SpecialistImpactOutput."""
        from src.reviewer.orchestrator import _run_cross_repo_reviewer

        impact_result = self._make_impact_result()
        ctx = self._make_context(impact_result=impact_result)

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(
            return_value=MagicMock(
                content=json.dumps(
                    {
                        "impact_warnings": [
                            {
                                "changed_file": "src/contracts/order.py",
                                "changed_entity": "OrderCreated",
                                "affected_service": "payment-worker",
                                "affected_repository": "payment-service",
                                "relationship_type": "CONSUMES",
                                "severity": "high",
                                "description": "Payment worker consumes this contract.",
                            }
                        ]
                    }
                )
            )
        )

        result = await _run_cross_repo_reviewer(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True, timeout=120
        )

        assert isinstance(result, SpecialistImpactOutput)
        assert len(result.impact_warnings) == 1
        assert result.impact_warnings[0].severity == "high"

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_parse_success_ignores_model_metadata(self, mock_openai_like, mock_agent_cls):
        from src.reviewer.orchestrator import _run_cross_repo_reviewer

        ctx = self._make_context(impact_result=self._make_impact_result())

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(
            return_value=MagicMock(
                content=json.dumps(
                    {
                        "impact_warnings": [
                            {
                                "changed_file": "src/contracts/order.py",
                                "changed_entity": "OrderCreated",
                                "affected_service": "payment-worker",
                                "affected_repository": "payment-service",
                                "relationship_type": "CONSUMES",
                                "severity": "high",
                                "description": "Payment worker consumes this contract.",
                            }
                        ],
                        "raw_content": "model-added",
                    }
                )
            )
        )

        result = await _run_cross_repo_reviewer(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True, timeout=120
        )

        assert isinstance(result, SpecialistImpactOutput)
        assert len(result.impact_warnings) == 1
        assert '"raw_content": "model-added"' in result.raw_content

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_parse_failure_returns_specialist_failure(self, mock_openai_like, mock_agent_cls):
        """Task 2.6 GREEN: parse failure returns SpecialistFailure with role."""
        from src.reviewer.orchestrator import _run_cross_repo_reviewer

        ctx = self._make_context(impact_result=self._make_impact_result())

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(return_value=MagicMock(content="not valid json"))

        result = await _run_cross_repo_reviewer(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True, timeout=120
        )

        assert isinstance(result, SpecialistFailure)
        assert result.role == "cross-repo-impact-reviewer"

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_timeout_returns_specialist_failure(self, mock_openai_like, mock_agent_cls):
        """Task 2.6 GREEN: timeout returns SpecialistFailure with reason."""
        import asyncio

        from src.reviewer.orchestrator import _run_cross_repo_reviewer

        ctx = self._make_context(impact_result=self._make_impact_result())

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        async def slow_run(*args, **kwargs):
            await asyncio.sleep(10)
            return MagicMock(content=json.dumps({"impact_warnings": []}))

        mock_agent.arun = slow_run

        result = await _run_cross_repo_reviewer(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True, timeout=0.1
        )

        assert isinstance(result, SpecialistFailure)
        assert result.role == "cross-repo-impact-reviewer"
        assert "timeout" in result.reason.lower()

    def test_parse_success_logs_specialist_output(self, caplog):
        """Observability: successful impact parse logs preview and counts."""
        import logging

        from src.reviewer.orchestrator import _parse_specialist_impact_output

        ctx = self._make_context(impact_result=self._make_impact_result())
        raw = json.dumps(
            {
                "impact_warnings": [
                    {
                        "changed_file": "src/f.py",
                        "changed_entity": "E",
                        "affected_service": "svc",
                        "affected_repository": "repo",
                        "relationship_type": "CONSUMES",
                        "severity": "high",
                        "description": "d",
                    }
                ]
            }
        )
        with caplog.at_level(logging.INFO):
            result = _parse_specialist_impact_output(raw, ctx)
        assert isinstance(result, SpecialistImpactOutput)
        logs = [r for r in caplog.records if "cross-repo-impact-reviewer" in r.getMessage()]
        assert len(logs) == 1
        msg = logs[0].getMessage()
        assert "impact_count" in msg
        assert "1" in msg
        assert "parse_failed" in msg

    def test_parse_empty_impact_json_logs_specialist_output(self, caplog):
        """Observability: empty impact JSON logs zero count."""
        import logging

        from src.reviewer.orchestrator import _parse_specialist_impact_output

        ctx = self._make_context(impact_result=self._make_impact_result())
        raw = json.dumps({"impact_warnings": []})
        with caplog.at_level(logging.INFO):
            _ = _parse_specialist_impact_output(raw, ctx)
        logs = [r for r in caplog.records if "cross-repo-impact-reviewer" in r.getMessage()]
        assert len(logs) == 1
        msg = logs[0].getMessage()
        assert "impact_count" in msg
        assert "0" in msg

    def test_parse_failure_logs_specialist_output(self, caplog):
        """Observability: impact parse failure logs preview with parse_failed=True."""
        import logging

        from src.reviewer.orchestrator import _parse_specialist_impact_output

        ctx = self._make_context(impact_result=self._make_impact_result())
        raw = "not valid json"
        with caplog.at_level(logging.INFO):
            result = _parse_specialist_impact_output(raw, ctx)
        assert isinstance(result, SpecialistFailure)
        logs = [r for r in caplog.records if "cross-repo-impact-reviewer" in r.getMessage()]
        assert len(logs) == 1
        msg = logs[0].getMessage()
        assert "parse_failed" in msg
