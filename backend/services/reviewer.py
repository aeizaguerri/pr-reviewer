"""Review service — bridges the HTTP API to the core reviewer agent."""

from src.reviewer.agent import review_pr_with_config
from backend.core.providers import SUPPORTS_STRUCTURED_OUTPUT, build_provider_config
from backend.models.schemas import (
    BugReportResponse,
    ImpactWarningResponse,
    ReviewRequest,
    ReviewResponse,
)


def _map_impact_warning(w) -> ImpactWarningResponse:
    """Map an ImpactWarning domain object to ImpactWarningResponse schema."""
    return ImpactWarningResponse(
        severity=w.severity,
        description=w.description,
    )


def run_review(req: ReviewRequest, api_key: str = "", github_token: str = "") -> ReviewResponse:
    """Execute a PR review using the given request configuration.

    Args:
        req: ReviewRequest with provider, model, and PR details.
        api_key: LLM provider API key (from Authorization header). Defaults to empty
            string — the provider config falls back to env vars when empty.
        github_token: GitHub personal access token (from X-GitHub-Token header).

    Returns:
        ReviewResponse with summary, approval, bugs, and impact warnings.
    """
    provider_config = build_provider_config(
        req.provider,
        req.model,
        api_key,
        req.base_url_override,
    )

    supports_structured_output = SUPPORTS_STRUCTURED_OUTPUT.get(req.provider, False)

    result = review_pr_with_config(
        owner=req.owner,
        repo=req.repo,
        pr_number=req.pr_number,
        provider_config=provider_config,
        supports_structured_output=supports_structured_output,
        github_token=github_token,
    )

    bugs = [
        BugReportResponse(
            file=bug.file,
            line=bug.line,
            severity=bug.severity,
            description=bug.description,
            suggestion=bug.suggestion,
        )
        for bug in result.bugs
    ]

    impact_warnings = [_map_impact_warning(w) for w in (result.impact_warnings or [])]

    return ReviewResponse(
        summary=result.summary,
        approved=result.approved,
        bugs=bugs,
        impact_warnings=impact_warnings,
    )
