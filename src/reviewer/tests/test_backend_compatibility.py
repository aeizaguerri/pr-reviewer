"""RED-phase tests: backend ReviewResponse compatibility (task 3.8 fixes)."""

from unittest.mock import patch

from backend.models.schemas import ReviewRequest
from src.reviewer.models import BugReport, ReviewOutput


class TestBackendCompatibility:
    def test_run_review_maps_fields_correctly(self):
        """Task 3.8: backend service maps ReviewOutput to ReviewResponse."""
        from backend.services.reviewer import run_review

        bug = BugReport(
            file="src/a.py",
            line=10,
            severity="major",
            description="bug",
            suggestion="fix",
        )
        review_output = ReviewOutput(
            summary="Found 1 bug",
            approved=False,
            bugs=[bug],
            impact_warnings=[],
        )

        req = ReviewRequest(
            owner="owner",
            repo="repo",
            pr_number=1,
            provider="cerebras",
        )

        with patch("backend.services.reviewer.agent_run_review") as mock_review:
            mock_review.return_value = review_output
            result = run_review(req, api_key="key", github_token="tok")

        assert result.summary == "Found 1 bug"
        assert result.approved is False
        assert len(result.bugs) == 1
        assert result.bugs[0].file == "src/a.py"
        assert len(result.impact_warnings) == 0

    def test_review_output_validates(self):
        """Task 3.8: ReviewOutput passes Pydantic validation."""
        output = ReviewOutput(
            summary="test",
            approved=True,
            bugs=[],
            impact_warnings=[],
        )
        assert output.summary == "test"
        assert output.approved is True
