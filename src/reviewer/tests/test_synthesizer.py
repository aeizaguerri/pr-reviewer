"""RED-phase tests: synthesizer → ReviewOutput (task 3.3)."""

from src.knowledge.models import ImpactWarning
from src.reviewer.models import (
    BugReport,
    ReviewContext,
    ReviewOutput,
)


class TestSynthesizer:
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

    def _make_bug(self, file: str, line: int, severity: str) -> BugReport:
        return BugReport(
            file=file,
            line=line,
            severity=severity,
            description="bug",
            suggestion="fix",
        )

    def test_merges_judged_and_security_bugs(self):
        """Task 3.3: judged bugs + security bugs both appear in output."""
        from src.reviewer.orchestrator import _synthesize

        judged = [self._make_bug("src/a.py", 10, "major").model_dump()]
        security = [self._make_bug("src/b.py", 20, "critical")]
        ctx = self._make_context()

        result = _synthesize(judged, security, [], ctx)
        assert len(result.bugs) == 2
        assert result.bugs[0].file == "src/a.py"
        assert result.bugs[1].file == "src/b.py"

    def test_no_duplicates_across_judged_and_security(self):
        """Task 3.3: same bug in judged and security is deduped."""
        from src.reviewer.orchestrator import _synthesize

        bug = self._make_bug("src/a.py", 10, "major")
        judged = [bug.model_dump()]
        security = [bug]
        ctx = self._make_context()

        result = _synthesize(judged, security, [], ctx)
        assert len(result.bugs) == 1

    def test_approved_false_when_critical_bug(self):
        """Task 3.3: critical bug → approved=False."""
        from src.reviewer.orchestrator import _synthesize

        judged = [self._make_bug("src/a.py", 10, "critical").model_dump()]
        ctx = self._make_context()

        result = _synthesize(judged, [], [], ctx)
        assert result.approved is False

    def test_approved_false_when_high_impact(self):
        """Task 3.3: high impact warning → approved=False."""
        from src.reviewer.orchestrator import _synthesize

        impact = [
            ImpactWarning(
                changed_file="src/a.py",
                changed_entity="OrderCreated",
                affected_service="svc",
                affected_repository="repo",
                relationship_type="CONSUMES",
                severity="high",
                description="breaks downstream",
            )
        ]
        ctx = self._make_context()

        result = _synthesize([], [], impact, ctx)
        assert result.approved is False

    def test_approved_true_when_empty(self):
        """Task 3.3: no bugs and no high impact → approved=True."""
        from src.reviewer.orchestrator import _synthesize

        ctx = self._make_context()
        result = _synthesize([], [], [], ctx)
        assert result.approved is True
        assert len(result.bugs) == 0

    def test_summary_is_non_empty(self):
        """Task 3.3: summary is a non-empty string."""
        from src.reviewer.orchestrator import _synthesize

        judged = [self._make_bug("src/a.py", 10, "major").model_dump()]
        ctx = self._make_context()

        result = _synthesize(judged, [], [], ctx)
        assert isinstance(result.summary, str)
        assert len(result.summary) > 0

    def test_validates_as_review_output(self):
        """Task 3.3: result is a valid ReviewOutput Pydantic model."""
        from src.reviewer.orchestrator import _synthesize

        judged = [self._make_bug("src/a.py", 10, "major").model_dump()]
        ctx = self._make_context()

        result = _synthesize(judged, [], [], ctx)
        assert isinstance(result, ReviewOutput)

    def test_graph_warnings_attached(self):
        """Task 3.3: impact_warnings from graph are present."""
        from src.reviewer.orchestrator import _synthesize

        impact = [
            ImpactWarning(
                changed_file="src/a.py",
                changed_entity="E",
                affected_service="svc",
                affected_repository="repo",
                relationship_type="CONSUMES",
                severity="medium",
                description="ok",
            )
        ]
        ctx = self._make_context()

        result = _synthesize([], [], impact, ctx)
        assert len(result.impact_warnings) == 1
        assert result.impact_warnings[0].severity == "medium"

    def test_approved_true_when_only_minor_bugs(self):
        """Task 3.3: minor-only bugs without high impact → approved=True."""
        from src.reviewer.orchestrator import _synthesize

        judged = [self._make_bug("src/a.py", 10, "minor").model_dump()]
        ctx = self._make_context()

        result = _synthesize(judged, [], [], ctx)
        assert result.approved is True
        assert len(result.bugs) == 1
        assert result.bugs[0].severity == "minor"

    def test_summary_includes_security_and_impact(self):
        """SYN-005: summary explicitly covers security, impact, and approval."""
        from src.knowledge.models import ImpactWarning
        from src.reviewer.orchestrator import _synthesize

        judged = [self._make_bug("src/a.py", 10, "major").model_dump()]
        security = [self._make_bug("src/b.py", 20, "critical")]
        impact = [
            ImpactWarning(
                changed_file="src/a.py",
                changed_entity="E",
                affected_service="svc",
                affected_repository="repo",
                relationship_type="CONSUMES",
                severity="high",
                description="breaks downstream",
            )
        ]
        ctx = self._make_context()

        result = _synthesize(judged, security, impact, ctx)
        assert "Security:" in result.summary
        assert "Impact:" in result.summary
        assert "Recommendation: changes requested" in result.summary

    def test_summary_recommends_approval_when_clean(self):
        """SYN-005: clean result recommends approval."""
        from src.reviewer.orchestrator import _synthesize

        ctx = self._make_context()
        result = _synthesize([], [], [], ctx)
        assert "Recommendation: approved" in result.summary
        assert "No bugs detected" in result.summary

    def test_judged_bug_and_security_overlap_merge_to_one(self):
        """SYN-002: judged major + security critical at same file/line → one critical entry."""
        from src.reviewer.orchestrator import _synthesize

        judged = [
            BugReport(
                file="src/api.py",
                line=42,
                severity="major",
                description="logic error here",
                suggestion="fix logic",
            ).model_dump()
        ]
        security = [
            BugReport(
                file="src/api.py",
                line=42,
                severity="critical",
                description="sql injection vulnerability",
                suggestion="use parameterized queries",
            )
        ]
        ctx = self._make_context()

        result = _synthesize(judged, security, [], ctx)
        assert len(result.bugs) == 1
        bug = result.bugs[0]
        assert bug.file == "src/api.py"
        assert bug.line == 42
        assert bug.severity == "critical"
        assert "logic error here" in bug.description
        assert "sql injection vulnerability" in bug.description
        assert "fix logic" in bug.suggestion
        assert "use parameterized queries" in bug.suggestion
