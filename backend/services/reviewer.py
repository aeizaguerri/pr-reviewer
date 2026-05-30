"""Review service — bridges the HTTP API to the core reviewer agent."""

from src.reviewer.agent import run_review as agent_run_review
from src.reviewer.models import ReviewRequest as DomainReviewRequest
from backend.core.providers import (
    resolve_public_hf_role_configs,
)
from backend.models.schemas import (
    BugReportResponse,
    ImpactWarningResponse,
    ReviewHealthResponse,
    ReviewRequest,
    ReviewResponse,
)


def _map_impact_warning(w) -> ImpactWarningResponse:
    """Map an ImpactWarning domain object to ImpactWarningResponse schema."""
    return ImpactWarningResponse(
        severity=w.severity,
        description=w.description,
        changed_file=getattr(w, "changed_file", ""),
        changed_entity=getattr(w, "changed_entity", ""),
        affected_service=getattr(w, "affected_service", ""),
        affected_repository=getattr(w, "affected_repository", ""),
        relationship_type=getattr(w, "relationship_type", ""),
    )


def run_review(req: ReviewRequest, api_key: str = "", github_token: str = "") -> ReviewResponse:
    """Execute a PR review using the given request configuration.

    Args:
        req: ReviewRequest with PR details. Compatibility fields (provider, model,
            base_url_override) are ignored for the public HF path.
        api_key: Hugging Face API key (from Authorization header). Used for all
            specialist agents in the public curated path.
        github_token: GitHub personal access token (from X-GitHub-Token header).

    Returns:
        ReviewResponse with summary, approval, bugs, and impact warnings.
    """
    role_configs = resolve_public_hf_role_configs(api_key)

    # Public HF path does not support structured output
    supports_structured_output = False

    domain_request = DomainReviewRequest(
        owner=req.owner,
        repo=req.repo,
        pr_number=req.pr_number,
        role_configs=role_configs,
        github_token=github_token,
        supports_structured_output=supports_structured_output,
    )

    result = agent_run_review(domain_request)

    bugs = [
        BugReportResponse(
            file=bug.file,
            line=bug.line,
            severity=bug.severity,
            description=bug.description,
            suggestion=bug.suggestion,
            category=getattr(bug, "category", "bug"),
            source=getattr(bug, "source", ""),
        )
        for bug in result.bugs
    ]

    impact_warnings = [_map_impact_warning(w) for w in (result.impact_warnings or [])]

    review_health = None
    if result.review_health is not None:
        review_health = ReviewHealthResponse(
            status=result.review_health.status,
            warnings=result.review_health.warnings,
        )

    return ReviewResponse(
        summary=result.summary,
        approved=result.approved,
        bugs=bugs,
        impact_warnings=impact_warnings,
        review_health=review_health,
    )
