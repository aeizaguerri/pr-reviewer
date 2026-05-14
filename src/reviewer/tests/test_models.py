"""TDD tests for reviewer models (Phase 1)."""

from src.reviewer.models import BugReport, ReviewHealth, ReviewOutput


class TestBugReportCategory:
    def test_bug_report_category_defaults_to_bug(self):
        """1.4: BugReport without category parses as category='bug'."""
        bug = BugReport(
            file="src/a.py",
            line=10,
            severity="major",
            description="bug",
            suggestion="fix",
        )
        assert bug.category == "bug"

    def test_bug_report_source_defaults_to_empty(self):
        """1.4: BugReport without source parses as source=''."""
        bug = BugReport(
            file="src/a.py",
            line=10,
            severity="major",
            description="bug",
            suggestion="fix",
        )
        assert bug.source == ""

    def test_bug_report_explicit_category_and_source(self):
        """1.4: Explicit category and source are preserved."""
        bug = BugReport(
            file="src/a.py",
            line=10,
            severity="major",
            description="bug",
            suggestion="fix",
            category="security",
            source="security-reviewer",
        )
        assert bug.category == "security"
        assert bug.source == "security-reviewer"


class TestReviewHealth:
    def test_review_health_defaults(self):
        """1.5: ReviewHealth defaults to status='complete' and empty warnings."""
        health = ReviewHealth()
        assert health.status == "complete"
        assert health.warnings == []

    def test_review_health_explicit_values(self):
        """1.5: ReviewHealth accepts explicit status and warnings."""
        health = ReviewHealth(
            status="degraded",
            warnings=["security reviewer timed out"],
        )
        assert health.status == "degraded"
        assert health.warnings == ["security reviewer timed out"]


class TestReviewOutputHealth:
    def test_review_output_review_health_is_optional(self):
        """1.6: ReviewOutput without review_health parses successfully."""
        output = ReviewOutput(
            summary="test",
            approved=True,
            bugs=[],
            impact_warnings=[],
        )
        assert output.review_health is None

    def test_review_output_review_health_accepted(self):
        """1.6: ReviewOutput accepts review_health explicitly."""
        health = ReviewHealth(status="partial", warnings=["specialist skipped"])
        output = ReviewOutput(
            summary="test",
            approved=True,
            bugs=[],
            impact_warnings=[],
            review_health=health,
        )
        assert output.review_health is not None
        assert output.review_health.status == "partial"
        assert output.review_health.warnings == ["specialist skipped"]
