"""RED-phase tests: ReviewContext builder (task 1.5)."""

from unittest.mock import patch

import pytest

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


class TestSafeContextDiagnostics:
    def test_diagnostics_include_all_four_fields(self, sample_diff, caplog):
        """Task 3.3 RED: safe diagnostics include lengths/counts and bounded path summary."""
        import logging

        from src.reviewer.orchestrator import _safe_context_summary

        with caplog.at_level(logging.DEBUG):
            result = _safe_context_summary(
                diff_text=sample_diff,
                shared_prompt="prompt text here",
                changed_paths=[
                    "src/a.py",
                    "src/b.py",
                    "src/c.py",
                    "src/d.py",
                    "src/e.py",
                    "src/f.py",
                ],
            )

        assert isinstance(result, dict)
        assert "diff_text_length" in result
        assert "shared_prompt_length" in result
        assert "changed_paths_count" in result
        assert "changed_paths_sample" in result
        assert result["diff_text_length"] == len(sample_diff)
        assert result["shared_prompt_length"] == len("prompt text here")
        assert result["changed_paths_count"] == 6
        assert len(result["changed_paths_sample"]) <= 5
        assert result["changed_paths_sample"] == [
            "src/a.py",
            "src/b.py",
            "src/c.py",
            "src/d.py",
            "src/e.py",
        ]

    def test_diagnostics_never_include_full_diff_body(self, sample_diff, caplog):
        """Task 3.4 RED: diagnostics must not leak full diff text or secrets."""
        import logging

        from src.reviewer.orchestrator import _safe_context_summary

        with caplog.at_level(logging.DEBUG):
            _safe_context_summary(
                diff_text=sample_diff,
                shared_prompt="prompt with secret-token-12345",
                changed_paths=["src/a.py"],
            )

        # The full diff body must not appear in any log record
        for record in caplog.records:
            assert sample_diff not in record.getMessage()
            assert "secret-token-12345" not in record.getMessage()

    def test_diagnostics_with_empty_diff_and_many_paths(self, caplog):
        """Triangulation: empty diff and many paths produce correct zero/short values."""
        import logging

        from src.reviewer.orchestrator import _safe_context_summary

        with caplog.at_level(logging.DEBUG):
            result = _safe_context_summary(
                diff_text="",
                shared_prompt="",
                changed_paths=[],
            )

        assert result["diff_text_length"] == 0
        assert result["shared_prompt_length"] == 0
        assert result["changed_paths_count"] == 0
        assert result["changed_paths_sample"] == []

    def test_diagnostics_path_sample_bounded_at_five(self, caplog):
        """Triangulation: sample is strictly bounded to first 5 paths."""
        import logging

        from src.reviewer.orchestrator import _safe_context_summary

        paths = [f"src/{i}.py" for i in range(10)]

        with caplog.at_level(logging.DEBUG):
            result = _safe_context_summary(
                diff_text="diff",
                shared_prompt="prompt",
                changed_paths=paths,
            )

        assert result["changed_paths_count"] == 10
        assert len(result["changed_paths_sample"]) == 5
        assert result["changed_paths_sample"] == paths[:5]


class TestRunBugPass:
    _PROVIDER_CONFIG = ("my-model", "https://api.example.com/v1", "sk-test")

    def _make_context(self, shared_prompt: str = "test prompt"):
        from src.reviewer.models import ReviewContext
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

    @pytest.mark.anyio
    async def test_run_bug_pass_returns_specialist_bug_output_on_success(self):
        """1.7: _run_bug_pass returns SpecialistBugOutput on successful agent run."""
        import json
        from unittest.mock import MagicMock
        from src.reviewer.orchestrator import _run_bug_pass

        ctx = self._make_context()
        mock_agent = MagicMock()
        mock_agent.arun = MagicMock(return_value=MagicMock(
            content=json.dumps({"bugs": []})
        ))

        result = await _run_bug_pass("bug-reviewer-a", ctx, mock_agent, timeout=10)
        assert result.provider == "bug-reviewer-a"
        assert result.parse_failed is False

    @pytest.mark.anyio
    async def test_run_bug_pass_returns_degraded_on_timeout(self, caplog):
        """1.7: _run_bug_pass returns degraded output and logs warning on timeout."""
        import asyncio
        import logging
        from unittest.mock import MagicMock
        from src.reviewer.orchestrator import _run_bug_pass

        ctx = self._make_context()
        mock_agent = MagicMock()

        async def slow_run(*args, **kwargs):
            await asyncio.sleep(10)
            return MagicMock(content="{}")

        mock_agent.arun = slow_run

        with caplog.at_level(logging.WARNING):
            result = await _run_bug_pass("bug-reviewer-a", ctx, mock_agent, timeout=0.1)

        assert result.provider == "bug-reviewer-a"
        assert result.parse_failed is True
        assert result.bugs == []
        assert any("timed out" in r.getMessage().lower() for r in caplog.records)

    @pytest.mark.anyio
    async def test_run_bug_pass_returns_degraded_on_exception(self, caplog):
        """1.7: _run_bug_pass returns degraded output and logs warning on exception."""
        import logging
        from unittest.mock import MagicMock
        from src.reviewer.orchestrator import _run_bug_pass

        ctx = self._make_context()
        mock_agent = MagicMock()

        async def failing_run(*args, **kwargs):
            raise RuntimeError("agent exploded")

        mock_agent.arun = failing_run

        with caplog.at_level(logging.WARNING):
            result = await _run_bug_pass("bug-reviewer-a", ctx, mock_agent, timeout=10)

        assert result.provider == "bug-reviewer-a"
        assert result.parse_failed is True
        assert result.bugs == []
        assert any("agent exploded" in r.getMessage().lower() for r in caplog.records)


class TestSpecialistOutputLogging:
    def test_safe_output_preview_normalizes_whitespace(self):
        """Preview collapses all whitespace runs to a single space."""
        from src.reviewer.orchestrator import _safe_output_preview

        raw = "  hello\n\nworld\t\t!  "
        assert _safe_output_preview(raw) == "hello world !"

    def test_safe_output_preview_truncates_long_output(self):
        """Preview is bounded to 200 chars plus ellipsis."""
        from src.reviewer.orchestrator import _safe_output_preview

        raw = "x" * 300
        preview = _safe_output_preview(raw)
        assert len(preview) == 203
        assert preview.endswith("...")

    def test_safe_output_preview_empty_string(self):
        """Preview handles empty string gracefully."""
        from src.reviewer.orchestrator import _safe_output_preview

        assert _safe_output_preview("") == ""

    def test_log_specialist_output_info_level_with_payload(self, caplog):
        """Successful parse logs role, length, preview, keys, counts at INFO."""
        import logging

        from src.reviewer.orchestrator import _log_specialist_output

        with caplog.at_level(logging.INFO):
            _log_specialist_output(
                role="bug-reviewer-a",
                raw='{"bugs": []}',
                payload={"bugs": []},
                parse_failed=False,
                bug_count=0,
            )
        assert len(caplog.records) == 1
        record = caplog.records[0]
        msg = record.getMessage()
        assert "bug-reviewer-a" in msg
        assert "raw_length" in msg
        assert "preview" in msg
        assert "top_level_keys" in msg
        assert "bug_count" in msg
        assert "parse_failed" in msg

    def test_log_specialist_output_failure_no_payload(self, caplog):
        """Parse failure logs role and parse_failed without top_level_keys."""
        import logging

        from src.reviewer.orchestrator import _log_specialist_output

        with caplog.at_level(logging.INFO):
            _log_specialist_output(
                role="security-reviewer",
                raw="not json",
                parse_failed=True,
            )
        assert len(caplog.records) == 1
        record = caplog.records[0]
        msg = record.getMessage()
        assert "security-reviewer" in msg
        assert "parse_failed" in msg
        assert "top_level_keys" not in msg
        assert "bug_count" not in msg

    def test_log_specialist_output_with_impact_count(self, caplog):
        """Impact reviewer logs impact_count instead of bug_count."""
        import logging

        from src.reviewer.orchestrator import _log_specialist_output

        with caplog.at_level(logging.INFO):
            _log_specialist_output(
                role="cross-repo-impact-reviewer",
                raw='{"impact_warnings": []}',
                payload={"impact_warnings": []},
                parse_failed=False,
                impact_count=0,
            )
        assert len(caplog.records) == 1
        record = caplog.records[0]
        msg = record.getMessage()
        assert "impact_count" in msg
        assert "bug_count" not in msg

    def test_log_specialist_output_payload_keys_visible_for_misshaped_json(self, caplog):
        """Mis-shaped JSON (e.g. findings instead of bugs) still exposes top_level_keys."""
        import logging

        from src.reviewer.orchestrator import _log_specialist_output

        with caplog.at_level(logging.INFO):
            _log_specialist_output(
                role="bug-reviewer-a",
                raw='{"findings": [{"desc": "x"}]}',
                payload={"findings": [{"desc": "x"}]},
                parse_failed=True,
            )
        assert len(caplog.records) == 1
        record = caplog.records[0]
        msg = record.getMessage()
        assert "findings" in msg


class TestRoleConfigValidation:
    @pytest.mark.anyio
    async def test_arun_rejects_stale_leader_role_config(self):
        """Remediate: arun_multi_agent_review must fail fast on stale 'leader' config."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        bad_configs = {
            "bug": ("m", "http://b", "k"),
            "security": ("m", "http://b", "k"),
            "cross_repo": ("m", "http://b", "k"),
            "leader": ("m", "http://b", "k"),
        }

        with pytest.raises(ValueError, match="leader"):
            await arun_multi_agent_review(
                owner="o", repo="r", pr_number=1, role_configs=bad_configs
            )

    @pytest.mark.anyio
    async def test_arun_rejects_missing_role_config(self):
        """Triangulation: missing roles must also fail fast at orchestrator boundary."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        incomplete = {
            "bug": ("m", "http://b", "k"),
            "security": ("m", "http://b", "k"),
        }

        with pytest.raises(ValueError, match="Missing"):
            await arun_multi_agent_review(
                owner="o", repo="r", pr_number=1, role_configs=incomplete
            )
