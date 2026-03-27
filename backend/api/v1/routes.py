"""API v1 routes for PR Code Reviewer backend."""

from fastapi import APIRouter

from backend.core.providers import get_all_providers
from backend.models.schemas import (
    HealthResponse,
    ProvidersResponse,
    ReviewRequest,
    ReviewResponse,
)
from backend.services.reviewer import run_review

router = APIRouter()


@router.post("/api/v1/review", response_model=ReviewResponse)
async def review_pr(req: ReviewRequest) -> ReviewResponse:
    """Run a code review on the given pull request."""
    return run_review(req)


@router.get("/api/v1/providers", response_model=ProvidersResponse)
async def list_providers() -> ProvidersResponse:
    """List all available LLM providers and their configurations."""
    return ProvidersResponse(providers=get_all_providers())


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check service health including Neo4j connectivity."""
    from src.knowledge.client import check_health

    neo4j_ok = check_health()
    return HealthResponse(status="ok", neo4j=neo4j_ok)
