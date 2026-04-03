"""API v1 routes for PR Code Reviewer backend."""

import re

from fastapi import APIRouter, Header, HTTPException

from backend.core.providers import get_all_providers
from backend.models.schemas import (
    HealthResponse,
    ProvidersResponse,
    ReviewRequest,
    ReviewResponse,
)
from backend.services.reviewer import run_review

router = APIRouter()


@router.post("/review", response_model=ReviewResponse)
def review_pr(
    req: ReviewRequest,
    authorization: str = Header(default=""),
    x_github_token: str = Header(...),
) -> ReviewResponse:
    """Run a code review on the given pull request."""
    api_key = re.sub(r"(?i)^bearer\s+", "", authorization).strip()
    if not x_github_token.strip():
        raise HTTPException(status_code=401, detail="X-GitHub-Token must be non-empty")
    return run_review(req, api_key=api_key, github_token=x_github_token)


@router.get("/providers", response_model=ProvidersResponse)
async def list_providers() -> ProvidersResponse:
    """List all available LLM providers and their configurations."""
    return ProvidersResponse(providers=get_all_providers())


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check service health including Neo4j connectivity."""
    from src.knowledge.client import check_health

    neo4j_ok = check_health()
    return HealthResponse(status="ok", neo4j=neo4j_ok)
