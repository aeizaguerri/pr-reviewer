"""RED-phase tests: ReviewContext builder (task 1.5)."""

from unittest.mock import patch

from src.knowledge.models import ImpactResult, ImpactWarning


class TestBuildReviewContext:
    def test_returns_review_context_with_all_fields(self):
        """Task 1.5 RED: build_review_context must return a fully populated ReviewContext."""
        from src.reviewer.orchestrator import build_review_context

        result = build_review_context(
            owner="owner",
            repo="repo",
            pr_number=1,
            head_sha="abc123",
            pr_title="Fix bug",
            diff_text="### file.py\n@@ -1 +1 @@\n-patch",
        )

        assert result.owner == "owner"
        assert result.repo == "repo"
        assert result.pr_number == 1
        assert result.head_sha == "abc123"
        assert result.pr_title == "Fix bug"
        assert result.diff_text == "### file.py\n@@ -1 +1 @@\n-patch"
        assert result.changed_paths == ["file.py"]
        assert "<pr_title>" in result.shared_prompt
        assert "<diff_content>" in result.shared_prompt

    @patch("src.reviewer.orchestrator._enrich_with_graph")
    def test_graph_enrichment_gated_by_config(self, mock_enrich):
        """Task 1.5 RED: _enrich_with_graph is invoked so Config gating is exercised."""
        from src.reviewer.orchestrator import build_review_context

        mock_enrich.return_value = ("", None)

        build_review_context(
            owner="o", repo="r", pr_number=1, head_sha="sha", pr_title="t", diff_text="diff"
        )

        mock_enrich.assert_called_once()

    @patch("src.reviewer.orchestrator._enrich_with_graph")
    def test_shared_prompt_includes_impact_section_when_available(self, mock_enrich):
        """Task 1.5 RED: shared_prompt must contain both impact section and XML wrapper."""
        from src.reviewer.orchestrator import build_review_context

        warning = ImpactWarning(
            changed_file="src/f.py",
            changed_entity="E",
            affected_service="svc",
            affected_repository="repo",
            relationship_type="CONSUMES",
            severity="high",
            description="impact",
        )
        impact_result = ImpactResult(warnings=[warning], query_time_ms=1.0)
        mock_enrich.return_value = ("## Cross-Repo Impact\n\n- item\n", impact_result)

        result = build_review_context(
            owner="o", repo="r", pr_number=1, head_sha="sha", pr_title="t", diff_text="diff"
        )

        assert "## Cross-Repo Impact" in result.shared_prompt
        assert "<pr_title>" in result.shared_prompt
        assert "<diff_content>" in result.shared_prompt
