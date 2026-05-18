"""RED-phase tests: judge / deduper (task 3.2)."""

from src.reviewer.models import (
    BugReport,
    ReviewContext,
    SpecialistBugOutput,
)


class TestJudgeDeduper:
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

    def _make_bug(self, file: str, line: int, severity: str, description: str) -> BugReport:
        return BugReport(
            file=file,
            line=line,
            severity=severity,
            description=description,
            suggestion="fix it",
        )

    def test_duplicate_bugs_collapse_to_one(self):
        """Task 3.2: same file/line/severity/description collapse."""
        from src.reviewer.orchestrator import _run_judge

        bug = self._make_bug("src/a.py", 10, "major", "Null pointer")
        out_a = SpecialistBugOutput(bugs=[bug])
        out_b = SpecialistBugOutput(bugs=[bug])
        ctx = self._make_context()

        result = _run_judge(out_a, out_b, ctx)
        assert len(result) == 1
        assert result[0]["file"] == "src/a.py"
        assert result[0]["line"] == 10

    def test_different_severity_escalates(self):
        """Task 3.2: minor + major on same spot → major wins."""
        from src.reviewer.orchestrator import _run_judge

        minor = self._make_bug("src/a.py", 10, "minor", "Null pointer")
        major = self._make_bug("src/a.py", 10, "major", "Null pointer")
        out_a = SpecialistBugOutput(bugs=[minor])
        out_b = SpecialistBugOutput(bugs=[major])
        ctx = self._make_context()

        result = _run_judge(out_a, out_b, ctx)
        assert len(result) == 1
        assert result[0]["severity"] == "major"

    def test_critical_wins_over_major(self):
        """Task 3.2: major + critical on same spot → critical wins."""
        from src.reviewer.orchestrator import _run_judge

        major = self._make_bug("src/a.py", 10, "major", "Null pointer")
        critical = self._make_bug("src/a.py", 10, "critical", "Null pointer")
        out_a = SpecialistBugOutput(bugs=[major])
        out_b = SpecialistBugOutput(bugs=[critical])
        ctx = self._make_context()

        result = _run_judge(out_a, out_b, ctx)
        assert len(result) == 1
        assert result[0]["severity"] == "critical"

    def test_distinct_bugs_preserved(self):
        """Task 3.2: different files or lines are kept separate."""
        from src.reviewer.orchestrator import _run_judge

        bug1 = self._make_bug("src/a.py", 10, "major", "Null pointer")
        bug2 = self._make_bug("src/b.py", 20, "major", "Off-by-one")
        out_a = SpecialistBugOutput(bugs=[bug1])
        out_b = SpecialistBugOutput(bugs=[bug2])
        ctx = self._make_context()

        result = _run_judge(out_a, out_b, ctx)
        assert len(result) == 2

    def test_deterministic_order(self):
        """Task 3.2: dedupe is deterministic by sort key."""
        from src.reviewer.orchestrator import _run_judge

        bug = self._make_bug("src/a.py", 10, "major", "Null pointer")
        out_a = SpecialistBugOutput(bugs=[bug])
        out_b = SpecialistBugOutput(bugs=[])
        ctx = self._make_context()

        result1 = _run_judge(out_a, out_b, ctx)
        result2 = _run_judge(out_b, out_a, ctx)
        assert len(result1) == len(result2) == 1
        assert result1[0]["file"] == result2[0]["file"]

    def test_returns_bugreport_shaped_dicts(self):
        """Task 3.2: output fields match BugReport keys."""
        from src.reviewer.orchestrator import _run_judge

        bug = self._make_bug("src/a.py", 10, "major", "Null pointer")
        out_a = SpecialistBugOutput(bugs=[bug])
        out_b = SpecialistBugOutput(bugs=[])
        ctx = self._make_context()

        result = _run_judge(out_a, out_b, ctx)
        assert set(result[0].keys()) >= {"file", "line", "severity", "description", "suggestion"}

    def test_same_line_different_wording_collapses_to_one(self):
        """BUG-002: same file/line with different wording → one result."""
        from src.reviewer.orchestrator import _run_judge

        bug_a = self._make_bug("src/a.py", 10, "major", "Null pointer dereference detected")
        bug_b = self._make_bug("src/a.py", 10, "major", "Possible null reference at this location")
        out_a = SpecialistBugOutput(bugs=[bug_a])
        out_b = SpecialistBugOutput(bugs=[bug_b])
        ctx = self._make_context()

        result = _run_judge(out_a, out_b, ctx)
        assert len(result) == 1
        assert result[0]["file"] == "src/a.py"
        assert result[0]["line"] == 10

    def test_same_line_different_wording_escalates_severity(self):
        """BUG-002: wording variant with severity difference → higher severity wins."""
        from src.reviewer.orchestrator import _run_judge

        bug_a = self._make_bug("src/a.py", 10, "minor", "Null pointer dereference detected")
        bug_b = self._make_bug("src/a.py", 10, "critical", "Possible null reference at this location")
        out_a = SpecialistBugOutput(bugs=[bug_a])
        out_b = SpecialistBugOutput(bugs=[bug_b])
        ctx = self._make_context()

        result = _run_judge(out_a, out_b, ctx)
        assert len(result) == 1
        assert result[0]["severity"] == "critical"

    def test_same_line_different_bug_type_preserved(self):
        """BUG-003: distinct bugs on same line must NOT collapse."""
        from src.reviewer.orchestrator import _run_judge

        bug_a = self._make_bug("src/a.py", 10, "major", "Null pointer dereference detected")
        bug_b = self._make_bug("src/a.py", 10, "minor", "Off-by-one error in loop boundary")
        out_a = SpecialistBugOutput(bugs=[bug_a])
        out_b = SpecialistBugOutput(bugs=[bug_b])
        ctx = self._make_context()

        result = _run_judge(out_a, out_b, ctx)
        assert len(result) == 2
        severities = {r["severity"] for r in result}
        assert severities == {"major", "minor"}
