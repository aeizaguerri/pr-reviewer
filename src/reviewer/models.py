from typing import Literal

from pydantic import BaseModel, Field

from src.knowledge.models import ImpactResult, ImpactWarning


class BugReport(BaseModel):
    file: str = Field(..., description="Path to the file containing the bug")
    line: int = Field(..., description="Line number where the bug occurs")
    severity: Literal["critical", "major", "minor"] = Field(
        ...,
        description="Bug severity: critical (data loss/security), major (broken logic), minor (style/performance)",
    )
    description: str = Field(..., description="Clear description of the bug found")
    suggestion: str = Field(..., description="Concrete suggestion to fix the bug")
    category: Literal["bug", "security"] = Field(default="bug", description="Finding category: bug or security")
    source: str = Field(default="", description="Source identifier of the specialist that produced this finding")


class ReviewHealth(BaseModel):
    status: Literal["complete", "partial", "degraded"] = Field(
        default="complete", description="Review health status indicating completeness"
    )
    warnings: list[str] = Field(default_factory=list, description="Human-readable warnings about review quality")


class ReviewOutput(BaseModel):
    summary: str = Field(..., description="Overall summary of the PR review")
    bugs: list[BugReport] = Field(default_factory=list, description="List of bugs found in the PR")
    approved: bool = Field(
        ..., description="True if the PR can be merged, False if it requires changes"
    )
    impact_warnings: list[ImpactWarning] = Field(
        default_factory=list,
        description="Cross-repo impact warnings from knowledge graph (not produced by LLM)",
    )
    review_health: ReviewHealth | None = Field(default=None, description="Optional review health metadata")


# ---------------------------------------------------------------------------
# Internal specialist output models (not exported from __init__)
# ---------------------------------------------------------------------------


class SpecialistBugOutput(BaseModel):
    """Output from a Bug-reviewer specialist."""

    bugs: list[BugReport] = Field(default_factory=list)
    provider: str = Field(default="")
    raw_content: str = Field(default="")
    parse_failed: bool = Field(default=False)


class SpecialistSecurityOutput(BaseModel):
    """Output from the Security-reviewer specialist."""

    bugs: list[BugReport] = Field(default_factory=list)
    raw_content: str = Field(default="")


class SpecialistImpactOutput(BaseModel):
    """Output from the Cross-Repo Impact reviewer."""

    impact_warnings: list[ImpactWarning] = Field(default_factory=list)
    raw_content: str = Field(default="")


class SpecialistBugPayload(BaseModel):
    """LLM-facing payload for a Bug-reviewer specialist."""

    bugs: list[BugReport] = Field(default_factory=list)


class SpecialistSecurityPayload(BaseModel):
    """LLM-facing payload for the Security-reviewer specialist."""

    bugs: list[BugReport] = Field(default_factory=list)


class SpecialistImpactPayload(BaseModel):
    """LLM-facing payload for the Cross-Repo Impact reviewer."""

    impact_warnings: list[ImpactWarning] = Field(default_factory=list)


class SpecialistFailure(BaseModel):
    """Marker for a specialist that failed or timed out."""

    role: str
    reason: str


class ReviewContext(BaseModel):
    """Immutable shared context built once before fan-out."""

    owner: str
    repo: str
    pr_number: int
    head_sha: str
    pr_title: str
    diff_text: str
    changed_paths: list[str]
    impact_result: ImpactResult | None = None
    shared_prompt: str = ""  # impact_section + _make_prompt()
