from unittest.mock import patch

from backend.models.schemas import ReviewRequest
from backend.services.reviewer import run_review
from src.reviewer.models import ReviewOutput


@patch("backend.services.reviewer.review_pr_with_config")
def test_run_review_normalizes_provider_for_structured_output(mock_review):
    mock_review.return_value = ReviewOutput(summary="ok", approved=True, bugs=[], impact_warnings=[])

    req = ReviewRequest(
        owner="o",
        repo="r",
        pr_number=1,
        provider="Cerebras",
        model="",
        base_url_override="",
    )

    run_review(req, api_key="hf-key", github_token="gh-token")

    assert mock_review.call_args.kwargs["supports_structured_output"] is True
