"""D.6 — Integration tests for review_pr() flow in src/reviewer/agent.py.

All external dependencies (Neo4j driver, Agno agent, fetch_pr_data) are mocked.
No running Neo4j or LLM endpoint is required.
"""

from unittest.mock import MagicMock, patch

import pytest

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


FAKE_DIFF = (
    "### src/contracts/order_created.py\n"
    "@@ -1,3 +1,4 @@\n"
    "-order_id: str\n"
    "+order_id: int\n"
)
FAKE_HEAD_SHA = "abc123"
FAKE_PR_TITLE = "chore: update order schema"


# ---------------------------------------------------------------------------
# Tests: ENABLE_GRAPH_ENRICHMENT=False
# ---------------------------------------------------------------------------


class TestReviewPrGraphEnrichmentDisabled:
    def test_no_graph_calls_when_enrichment_disabled(
        self, graph_enrichment_disabled, monkeypatch
    ):
        """When ENABLE_GRAPH_ENRICHMENT=False, no Neo4j operations must occur."""
        mock_review_output = _make_review_output()

        with (
            patch("src.reviewer.agent.fetch_pr_data") as mock_fetch,
            patch("src.reviewer.agent._build_agent") as mock_build_agent,
            patch("src.reviewer.agent.post_review_comments"),
        ):
            mock_fetch.return_value = (FAKE_DIFF, FAKE_HEAD_SHA, FAKE_PR_TITLE)
            mock_run = MagicMock()
            mock_run.content = mock_review_output
            mock_build_agent.return_value.run = MagicMock(return_value=mock_run)

            # Spy on knowledge module imports to verify they are never called
            with patch("src.knowledge.client.check_health") as mock_check_health:
                from src.reviewer.agent import review_pr
                result = review_pr("owner", "repo", 1)

                # check_health must NOT have been called
                mock_check_health.assert_not_called()

        assert result.impact_warnings == []

    def test_result_has_no_impact_warnings_when_disabled(
        self, graph_enrichment_disabled
    ):
        mock_review_output = _make_review_output()

        with (
            patch("src.reviewer.agent.fetch_pr_data") as mock_fetch,
            patch("src.reviewer.agent._build_agent") as mock_build_agent,
            patch("src.reviewer.agent.post_review_comments"),
        ):
            mock_fetch.return_value = (FAKE_DIFF, FAKE_HEAD_SHA, FAKE_PR_TITLE)
            mock_run = MagicMock()
            mock_run.content = mock_review_output
            mock_build_agent.return_value.run = MagicMock(return_value=mock_run)

            from src.reviewer.agent import review_pr
            result = review_pr("owner", "repo", 1)

        assert result.impact_warnings == []


# ---------------------------------------------------------------------------
# Tests: ENABLE_GRAPH_ENRICHMENT=True, Neo4j down
# ---------------------------------------------------------------------------


class TestReviewPrNeo4jDown:
    def test_review_proceeds_normally_when_neo4j_down(
        self, graph_enrichment_enabled, monkeypatch
    ):
        """When Neo4j is unreachable, review must complete without impact warnings."""
        mock_review_output = _make_review_output()

        with (
            patch("src.reviewer.agent.fetch_pr_data") as mock_fetch,
            patch("src.reviewer.agent._build_agent") as mock_build_agent,
            patch("src.reviewer.agent.post_review_comments"),
        ):
            mock_fetch.return_value = (FAKE_DIFF, FAKE_HEAD_SHA, FAKE_PR_TITLE)
            mock_run = MagicMock()
            mock_run.content = mock_review_output
            mock_build_agent.return_value.run = MagicMock(return_value=mock_run)

            # Patch check_health inside the reviewer.agent module's import scope
            with patch("src.knowledge.client.check_health", return_value=False):
                from src.reviewer.agent import review_pr
                result = review_pr("owner", "repo", 1)

        assert isinstance(result, ReviewOutput)
        assert result.impact_warnings == []

    def test_impact_warnings_empty_when_neo4j_down(
        self, graph_enrichment_enabled
    ):
        """result.impact_warnings must be [] when Neo4j health check returns False."""
        mock_review_output = _make_review_output()

        with (
            patch("src.reviewer.agent.fetch_pr_data") as mock_fetch,
            patch("src.reviewer.agent._build_agent") as mock_build_agent,
            patch("src.reviewer.agent.post_review_comments"),
        ):
            mock_fetch.return_value = (FAKE_DIFF, FAKE_HEAD_SHA, FAKE_PR_TITLE)
            mock_run = MagicMock()
            mock_run.content = mock_review_output
            mock_build_agent.return_value.run = MagicMock(return_value=mock_run)

            with patch("src.knowledge.client.check_health", return_value=False):
                from src.reviewer.agent import review_pr
                result = review_pr("owner", "repo", 1)

        assert result.impact_warnings == []


# ---------------------------------------------------------------------------
# Tests: ENABLE_GRAPH_ENRICHMENT=True, Neo4j healthy, warnings returned
# ---------------------------------------------------------------------------


class TestReviewPrWithGraphWarnings:
    def test_impact_warnings_attached_to_result(
        self, graph_enrichment_enabled
    ):
        """When graph returns warnings, they must be attached to ReviewOutput."""
        mock_review_output = _make_review_output()
        warning = _make_impact_warning()
        impact_result = ImpactResult(warnings=[warning], query_time_ms=5.0)

        with (
            patch("src.reviewer.agent.fetch_pr_data") as mock_fetch,
            patch("src.reviewer.agent._build_agent") as mock_build_agent,
            patch("src.reviewer.agent.post_review_comments"),
        ):
            mock_fetch.return_value = (FAKE_DIFF, FAKE_HEAD_SHA, FAKE_PR_TITLE)
            mock_run = MagicMock()
            mock_run.content = mock_review_output
            mock_build_agent.return_value.run = MagicMock(return_value=mock_run)

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

    def test_impact_section_injected_into_prompt(
        self, graph_enrichment_enabled
    ):
        """When warnings are present, the impact section must be prepended to the prompt."""
        mock_review_output = _make_review_output()
        warning = _make_impact_warning()
        impact_result = ImpactResult(warnings=[warning], query_time_ms=5.0)

        captured_prompts: list[str] = []

        def capture_run(prompt: str):
            captured_prompts.append(prompt)
            mock_run = MagicMock()
            mock_run.content = mock_review_output
            return mock_run

        with (
            patch("src.reviewer.agent.fetch_pr_data") as mock_fetch,
            patch("src.reviewer.agent._build_agent") as mock_build_agent,
            patch("src.reviewer.agent.post_review_comments"),
        ):
            mock_fetch.return_value = (FAKE_DIFF, FAKE_HEAD_SHA, FAKE_PR_TITLE)
            mock_build_agent.return_value.run = MagicMock(side_effect=capture_run)

            with (
                patch("src.knowledge.client.check_health", return_value=True),
                patch("src.knowledge.client.get_driver", return_value=MagicMock()),
                patch(
                    "src.knowledge.queries.find_consumers_of_paths",
                    return_value=impact_result,
                ),
            ):
                from src.reviewer.agent import review_pr
                review_pr("owner", "repo", 1)

        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        assert "## Cross-Repository Impact Analysis" in prompt
        # Impact section must appear BEFORE the diff content
        impact_pos = prompt.index("## Cross-Repository Impact Analysis")
        diff_pos = prompt.index("PR title:")
        assert impact_pos < diff_pos

    def test_bugs_and_summary_unaffected_by_impact_warnings(
        self, graph_enrichment_enabled
    ):
        """impact_warnings must not overwrite bugs or summary in ReviewOutput."""
        mock_review_output = _make_review_output(with_bug=True)
        warning = _make_impact_warning()
        impact_result = ImpactResult(warnings=[warning])

        with (
            patch("src.reviewer.agent.fetch_pr_data") as mock_fetch,
            patch("src.reviewer.agent._build_agent") as mock_build_agent,
            patch("src.reviewer.agent.post_review_comments"),
        ):
            mock_fetch.return_value = (FAKE_DIFF, FAKE_HEAD_SHA, FAKE_PR_TITLE)
            mock_run = MagicMock()
            mock_run.content = mock_review_output
            mock_build_agent.return_value.run = MagicMock(return_value=mock_run)

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

        assert result.summary == "PR looks okay."
        assert len(result.bugs) == 1
        assert result.bugs[0].file == "src/main.py"
        assert len(result.impact_warnings) == 1


# ---------------------------------------------------------------------------
# Tests: graceful degradation on unexpected graph error
# ---------------------------------------------------------------------------


class TestReviewPrGraphError:
    def test_review_proceeds_on_unexpected_graph_exception(
        self, graph_enrichment_enabled
    ):
        """An unexpected exception during graph enrichment must not propagate."""
        mock_review_output = _make_review_output()

        with (
            patch("src.reviewer.agent.fetch_pr_data") as mock_fetch,
            patch("src.reviewer.agent._build_agent") as mock_build_agent,
            patch("src.reviewer.agent.post_review_comments"),
        ):
            mock_fetch.return_value = (FAKE_DIFF, FAKE_HEAD_SHA, FAKE_PR_TITLE)
            mock_run = MagicMock()
            mock_run.content = mock_review_output
            mock_build_agent.return_value.run = MagicMock(return_value=mock_run)

            with patch(
                "src.knowledge.client.check_health",
                side_effect=RuntimeError("Unexpected internal error"),
            ):
                from src.reviewer.agent import review_pr
                # Must NOT raise
                result = review_pr("owner", "repo", 1)

        assert isinstance(result, ReviewOutput)
        assert result.impact_warnings == []
