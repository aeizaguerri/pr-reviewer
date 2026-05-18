"""D.6 — Integration tests for review_pr() flow.

review_pr() now delegates to the multi-agent orchestrator. All external
dependencies (Neo4j driver, Agno agents, fetch_pr_data) are mocked at the
orchestrator boundary. No running Neo4j or LLM endpoint is required.
"""

from unittest.mock import MagicMock, patch

from src.knowledge.models import ImpactResult, ImpactWarning
from src.reviewer.models import BugReport, ReviewOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_review_output(with_bug: bool = False) -> ReviewOutput:
    bugs = []
    if with_bug:
        bugs = [
            BugReport(
                file="src/main.py",
                line=10,
                severity="minor",
                description="Unused variable",
                suggestion="Remove it.",
            )
        ]
    return ReviewOutput(
        summary="PR looks okay.",
        bugs=bugs,
        approved=not with_bug,
        impact_warnings=[],
    )


def _make_impact_warning() -> ImpactWarning:
    return ImpactWarning(
        changed_file="src/contracts/order_created.py",
        changed_entity="OrderCreatedEvent",
        affected_service="payment-worker",
        affected_repository="payment-service",
        relationship_type="CONSUMES",
        severity="medium",
        description="`payment-worker` consumes `OrderCreatedEvent`.",
    )


FAKE_DIFF = "### src/contracts/order_created.py\n@@ -1,3 +1,4 @@\n-order_id: str\n+order_id: int\n"
FAKE_HEAD_SHA = "abc123"
FAKE_PR_TITLE = "chore: update order schema"


# ---------------------------------------------------------------------------
# Tests: ENABLE_GRAPH_ENRICHMENT=False
# ---------------------------------------------------------------------------


class TestReviewPrGraphEnrichmentDisabled:
    def test_no_graph_calls_when_enrichment_disabled(self, graph_enrichment_disabled, monkeypatch):
        """When ENABLE_GRAPH_ENRICHMENT=False, no Neo4j operations must occur."""
        mock_review_output = _make_review_output()

        with (
            patch("src.reviewer.orchestrator.fetch_pr_data") as mock_fetch,
            patch("src.reviewer.orchestrator.run_multi_agent_review") as mock_orch,
        ):
            mock_fetch.return_value = (FAKE_DIFF, FAKE_HEAD_SHA, FAKE_PR_TITLE)
            mock_orch.return_value = mock_review_output

            # Spy on knowledge module imports to verify they are never called
            with patch("src.knowledge.client.check_health") as mock_check_health:
                from src.reviewer.agent import review_pr

                result = review_pr("owner", "repo", 1)

                # check_health must NOT have been called
                mock_check_health.assert_not_called()

        assert result.impact_warnings == []

    def test_result_has_no_impact_warnings_when_disabled(self, graph_enrichment_disabled):
        mock_review_output = _make_review_output()

        with (
            patch("src.reviewer.orchestrator.fetch_pr_data") as mock_fetch,
            patch("src.reviewer.orchestrator.run_multi_agent_review") as mock_orch,
        ):
            mock_fetch.return_value = (FAKE_DIFF, FAKE_HEAD_SHA, FAKE_PR_TITLE)
            mock_orch.return_value = mock_review_output

            from src.reviewer.agent import review_pr

            result = review_pr("owner", "repo", 1)

        assert result.impact_warnings == []


# ---------------------------------------------------------------------------
# Tests: ENABLE_GRAPH_ENRICHMENT=True, Neo4j down
# ---------------------------------------------------------------------------


class TestReviewPrNeo4jDown:
    def test_review_proceeds_normally_when_neo4j_down(self, graph_enrichment_enabled, monkeypatch):
        """When Neo4j is unreachable, review must complete without impact warnings."""
        mock_review_output = _make_review_output()

        with (
            patch("src.reviewer.orchestrator.fetch_pr_data") as mock_fetch,
            patch("src.reviewer.orchestrator.run_multi_agent_review") as mock_orch,
        ):
            mock_fetch.return_value = (FAKE_DIFF, FAKE_HEAD_SHA, FAKE_PR_TITLE)
            mock_orch.return_value = mock_review_output

            # Patch check_health inside the reviewer.agent module's import scope
            with patch("src.knowledge.client.check_health", return_value=False):
                from src.reviewer.agent import review_pr

                result = review_pr("owner", "repo", 1)

        assert isinstance(result, ReviewOutput)
        assert result.impact_warnings == []

    def test_impact_warnings_empty_when_neo4j_down(self, graph_enrichment_enabled):
        """result.impact_warnings must be [] when Neo4j health check returns False."""
        mock_review_output = _make_review_output()

        with (
            patch("src.reviewer.orchestrator.fetch_pr_data") as mock_fetch,
            patch("src.reviewer.orchestrator.run_multi_agent_review") as mock_orch,
        ):
            mock_fetch.return_value = (FAKE_DIFF, FAKE_HEAD_SHA, FAKE_PR_TITLE)
            mock_orch.return_value = mock_review_output

            with patch("src.knowledge.client.check_health", return_value=False):
                from src.reviewer.agent import review_pr

                result = review_pr("owner", "repo", 1)

        assert result.impact_warnings == []


# ---------------------------------------------------------------------------
# Tests: ENABLE_GRAPH_ENRICHMENT=True, Neo4j healthy, warnings returned
# ---------------------------------------------------------------------------


class TestReviewPrWithGraphWarnings:
    def test_impact_warnings_attached_to_result(self, graph_enrichment_enabled):
        """When graph returns warnings, they must be attached to ReviewOutput."""
        warning = _make_impact_warning()
        impact_result = ImpactResult(warnings=[warning], query_time_ms=5.0)

        with (
            patch("src.reviewer.orchestrator.fetch_pr_data") as mock_fetch,
            patch("src.reviewer.orchestrator._run_bug_reviewers") as mock_bug,
            patch("src.reviewer.orchestrator._run_security_reviewer") as mock_sec,
            patch("src.reviewer.orchestrator._run_cross_repo_reviewer") as mock_cross,
        ):
            mock_fetch.return_value = (FAKE_DIFF, FAKE_HEAD_SHA, FAKE_PR_TITLE)
            from src.reviewer.models import (
                SpecialistBugOutput,
                SpecialistSecurityOutput,
                SpecialistImpactOutput,
            )

            mock_bug.return_value = (SpecialistBugOutput(bugs=[]), SpecialistBugOutput(bugs=[]))
            mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
            mock_cross.return_value = SpecialistImpactOutput(impact_warnings=[])

            with (
                patch("src.knowledge.client.check_health", return_value=True),
                patch("src.knowledge.client.get_driver", return_value=MagicMock()),
                patch(
                    "src.knowledge.queries.find_consumers_of_paths",
                    return_value=impact_result,
                ),
            ):
                from src.reviewer.agent import review_pr

                result = review_pr("owner", "repo", 1)

        assert len(result.impact_warnings) == 1
        assert result.impact_warnings[0].affected_service == "payment-worker"

    def test_bugs_and_summary_unaffected_by_impact_warnings(self, graph_enrichment_enabled):
        """impact_warnings must not overwrite bugs or summary in ReviewOutput."""
        mock_review_output = _make_review_output(with_bug=True)
        warning = _make_impact_warning()
        impact_result = ImpactResult(warnings=[warning])

        with (
            patch("src.reviewer.orchestrator.fetch_pr_data") as mock_fetch,
            patch("src.reviewer.orchestrator._run_bug_reviewers") as mock_bug,
            patch("src.reviewer.orchestrator._run_security_reviewer") as mock_sec,
            patch("src.reviewer.orchestrator._run_cross_repo_reviewer") as mock_cross,
        ):
            mock_fetch.return_value = (FAKE_DIFF, FAKE_HEAD_SHA, FAKE_PR_TITLE)
            from src.reviewer.models import (
                SpecialistBugOutput,
                SpecialistSecurityOutput,
                SpecialistImpactOutput,
            )

            mock_bug.return_value = (
                SpecialistBugOutput(bugs=mock_review_output.bugs),
                SpecialistBugOutput(bugs=[]),
            )
            mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
            mock_cross.return_value = SpecialistImpactOutput(impact_warnings=[])

            with (
                patch("src.knowledge.client.check_health", return_value=True),
                patch("src.knowledge.client.get_driver", return_value=MagicMock()),
                patch(
                    "src.knowledge.queries.find_consumers_of_paths",
                    return_value=impact_result,
                ),
            ):
                from src.reviewer.agent import review_pr

                result = review_pr("owner", "repo", 1)

        # Summary is generated by synthesizer, not preserved from mock
        assert len(result.bugs) == 1
        assert result.bugs[0].file == "src/main.py"
        assert len(result.impact_warnings) == 1


# ---------------------------------------------------------------------------
# Tests: graceful degradation on unexpected graph error
# ---------------------------------------------------------------------------


class TestReviewPrGraphError:
    def test_review_proceeds_on_unexpected_graph_exception(self, graph_enrichment_enabled):
        """An unexpected exception during graph enrichment must not propagate."""
        mock_review_output = _make_review_output()

        with (
            patch("src.reviewer.orchestrator.fetch_pr_data") as mock_fetch,
            patch("src.reviewer.orchestrator.run_multi_agent_review") as mock_orch,
        ):
            mock_fetch.return_value = (FAKE_DIFF, FAKE_HEAD_SHA, FAKE_PR_TITLE)
            mock_orch.return_value = mock_review_output

            with patch(
                "src.knowledge.client.check_health",
                side_effect=RuntimeError("Unexpected internal error"),
            ):
                from src.reviewer.agent import review_pr

                # Must NOT raise
                result = review_pr("owner", "repo", 1)

        assert isinstance(result, ReviewOutput)
        assert result.impact_warnings == []
