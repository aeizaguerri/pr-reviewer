from typing import Literal

from pydantic import BaseModel, Field


class BugReport(BaseModel):
    file: str = Field(..., description="Path to the file containing the bug")
    line: int = Field(..., description="Line number where the bug occurs")
    severity: Literal["critical", "major", "minor"] = Field(
        ..., description="Bug severity: critical (data loss/security), major (broken logic), minor (style/performance)"
    )
    description: str = Field(..., description="Clear description of the bug found")
    suggestion: str = Field(..., description="Concrete suggestion to fix the bug")


class ReviewOutput(BaseModel):
    summary: str = Field(..., description="Overall summary of the PR review")
    bugs: list[BugReport] = Field(default_factory=list, description="List of bugs found in the PR")
    approved: bool = Field(..., description="True if the PR can be merged, False if it requires changes")
