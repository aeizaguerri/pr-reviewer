"""Tests for frontend render helpers (Phase 4)."""

from frontend.render_helpers import format_bug_row, format_review_health, group_findings_by_category


class TestGroupFindingsByCategory:
    def test_groups_findings_by_explicit_category(self):
        """4.2: bugs with explicit category are grouped correctly."""
        bugs = [
            {"file": "a.py", "line": 1, "category": "bug", "severity": "major"},
            {"file": "b.py", "line": 2, "category": "security", "severity": "critical"},
            {"file": "c.py", "line": 3, "category": "bug", "severity": "minor"},
        ]
        groups = group_findings_by_category(bugs)
        assert len(groups["bug"]) == 2
        assert len(groups["security"]) == 1
        assert groups["security"][0]["file"] == "b.py"

    def test_missing_category_defaults_to_bugs(self):
        """4.3: bugs without category default to 'bug' group."""
        bugs = [
            {"file": "a.py", "line": 1, "severity": "major"},
            {"file": "b.py", "line": 2, "category": "security", "severity": "critical"},
        ]
        groups = group_findings_by_category(bugs)
        assert len(groups["bug"]) == 1
        assert len(groups["security"]) == 1
        assert groups["bug"][0]["file"] == "a.py"

    def test_empty_category_defaults_to_bugs(self):
        """4.3: empty string category defaults to 'bug' group."""
        bugs = [
            {"file": "a.py", "line": 1, "category": "", "severity": "major"},
        ]
        groups = group_findings_by_category(bugs)
        assert len(groups["bug"]) == 1


class TestFormatReviewHealth:
    def test_renders_review_health_section(self):
        """4.1: review health is formatted for display."""
        health = {"status": "partial", "warnings": ["cross-repo skipped"]}
        formatted = format_review_health(health)
        assert formatted is not None
        assert formatted["status"] == "partial"
        assert formatted["warnings"] == ["cross-repo skipped"]

    def test_none_review_health_returns_none(self):
        """4.1: absent review health returns None."""
        assert format_review_health(None) is None

    def test_defaults_for_minimal_health(self):
        """4.1: minimal health dict gets sensible defaults."""
        formatted = format_review_health({})
        assert formatted is not None
        assert formatted["status"] == "complete"
        assert formatted["warnings"] == []


class TestFormatBugRow:
    def test_format_bug_row_includes_key_fields(self):
        bug = {
            "file": "src/a.py",
            "line": 10,
            "severity": "major",
            "description": "logic error",
            "suggestion": "fix it",
        }
        row = format_bug_row(bug)
        assert row["File"] == "src/a.py"
        assert row["Line"] == 10
        assert "major" in row["Severity"]
        assert row["Description"] == "logic error"
        assert row["Suggestion"] == "fix it"


class TestBuildReviewDisplay:
    def test_builds_all_sections_for_mixed_findings(self):
        """Render path computes bugs, security, impact, health, and approval."""
        from frontend.render_helpers import build_review_display

        result = {
            "approved": False,
            "summary": "Found issues",
            "bugs": [
                {"file": "a.py", "line": 1, "severity": "major", "description": "d1", "suggestion": "s1", "category": "bug"},
                {"file": "b.py", "line": 2, "severity": "critical", "description": "d2", "suggestion": "s2", "category": "security"},
            ],
            "impact_warnings": [
                {"changed_file": "c.py", "affected_service": "svc", "affected_repository": "repo", "severity": "high", "description": "breaks"},
            ],
            "review_health": {"status": "partial", "warnings": ["cross-repo skipped"]},
        }
        display = build_review_display(result)
        assert display["approved"] is False
        assert display["approval_label"] == "❌ Changes Requested"
        assert display["approval_delta"] == "Requires changes"
        assert display["summary"] == "Found issues"
        assert display["health"]["status"] == "partial"
        assert len(display["bug_rows"]) == 1
        assert display["bug_rows"][0]["File"] == "a.py"
        assert len(display["security_rows"]) == 1
        assert display["security_rows"][0]["File"] == "b.py"
        assert len(display["impact_warnings"]) == 1
        assert display["impact_warnings"][0]["changed_file"] == "c.py"

    def test_builds_clean_display_when_no_findings(self):
        """Render path handles clean result with no bugs or warnings."""
        from frontend.render_helpers import build_review_display

        result = {
            "approved": True,
            "summary": "No bugs detected.",
            "bugs": [],
            "impact_warnings": [],
            "review_health": {"status": "complete", "warnings": []},
        }
        display = build_review_display(result)
        assert display["approved"] is True
        assert display["approval_label"] == "✅ Approved"
        assert display["approval_delta"] == "Ready to merge"
        assert display["health"]["status"] == "complete"
        assert display["bug_rows"] == []
        assert display["security_rows"] == []
        assert display["impact_warnings"] == []

    def test_defaults_missing_review_health_to_complete(self):
        """Render path shows health even when no health is present."""
        from frontend.render_helpers import build_review_display

        result = {"approved": True, "summary": "Clean", "bugs": [], "impact_warnings": []}
        display = build_review_display(result)
        assert display["health"] is None
