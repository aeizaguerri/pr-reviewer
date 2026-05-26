from unittest.mock import patch

from backend.models.schemas import ReviewRequest
from backend.services.reviewer import run_review
from src.reviewer.models import ReviewOutput


@patch("backend.services.reviewer.review_pr_with_config")
def test_run_review_uses_public_hf_role_configs(mock_review):
    mock_review.return_value = ReviewOutput(summary="ok", approved=True, bugs=[], impact_warnings=[])

    req = ReviewRequest(
        owner="o",
        repo="r",
        pr_number=1,
        provider="cerebras",
        model="",
        base_url_override="",
    )

    run_review(req, api_key="hf-key", github_token="gh-token")

    # Public HF path does not support structured output
    assert mock_review.call_args.kwargs["supports_structured_output"] is False
    # Role configs dict is passed through
    role_configs = mock_review.call_args.kwargs["role_configs"]
    assert role_configs is not None
    assert "bug" in role_configs
    assert "security" in role_configs
    assert "cross_repo" in role_configs
    assert "leader" in role_configs
    # All roles use the request-scoped HF key
    for role, (_model, _base_url, api_key) in role_configs.items():
        assert api_key == "hf-key"


@patch("backend.services.reviewer.review_pr_with_config")
def test_run_review_ignores_request_provider_model_fields(mock_review):
    """Compatibility fields in the request body are ignored for the public path."""
    mock_review.return_value = ReviewOutput(summary="ok", approved=True, bugs=[], impact_warnings=[])

    req = ReviewRequest(
        owner="o",
        repo="r",
        pr_number=1,
        provider="openai",
        model="gpt-4o",
        base_url_override="https://custom.openai.com/v1",
    )

    run_review(req, api_key="hf-key", github_token="gh-token")

    # Should still use HF path, not OpenAI
    assert mock_review.call_args.kwargs["supports_structured_output"] is False
    role_configs = mock_review.call_args.kwargs["role_configs"]
    for role, (model_id, base_url, _api_key) in role_configs.items():
        assert "openai" not in base_url.lower()
