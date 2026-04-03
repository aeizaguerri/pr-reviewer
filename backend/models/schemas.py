from pydantic import BaseModel, ConfigDict, Field


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    owner: str
    repo: str
    pr_number: int = Field(..., gt=0)
    provider: str = "cerebras"
    model: str = ""
    base_url_override: str = ""


class BugReportResponse(BaseModel):
    file: str
    line: int
    severity: str
    description: str
    suggestion: str


class ImpactWarningResponse(BaseModel):
    severity: str
    description: str


class ReviewResponse(BaseModel):
    summary: str
    approved: bool
    bugs: list[BugReportResponse]
    impact_warnings: list[ImpactWarningResponse]


class ProviderInfo(BaseModel):
    key: str
    description: str
    default_model: str
    key_label: str
    supports_structured_output: bool


class ProvidersResponse(BaseModel):
    providers: list[ProviderInfo]


class HealthResponse(BaseModel):
    status: str
    neo4j: bool
