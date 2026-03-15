"""Pydantic models for the knowledge graph topology and impact analysis.

Defines two model families:
- **Topology models**: represent the YAML-defined service topology
  (RepositoryNode → ServiceNode → ContractNode → SchemaNode → FieldNode).
- **Impact models**: represent cross-repo impact warnings surfaced during review.
"""

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Topology node models (map 1:1 to YAML structure)
# ---------------------------------------------------------------------------


class FieldDef(BaseModel):
    """A single field within a schema definition."""

    name: str = Field(..., description="Field name")
    type: str = Field(..., description="Field type (e.g. 'str', 'float', 'list[OrderItem]')")
    required: bool = Field(default=True, description="Whether the field is required")


class SchemaDef(BaseModel):
    """A data-structure definition within a contract."""

    name: str = Field(..., description="Schema name (unique)")
    file_path: str = Field(default="", description="Repo-relative path to the schema source file")
    fields: list[FieldDef] = Field(default_factory=list, description="Fields in this schema")


class ContractDef(BaseModel):
    """An API, event, or message contract produced by a service."""

    name: str = Field(..., description="Contract name (unique)")
    file_path: str = Field(default="", description="Repo-relative path to the contract source file")
    type: str = Field(default="event", description="Contract type: event | api | message")
    schemas: list[SchemaDef] = Field(default_factory=list, description="Schemas defined by this contract")


class ServiceDef(BaseModel):
    """A deployable service within a repository."""

    name: str = Field(..., description="Service name (unique)")
    description: str = Field(default="", description="Brief description of the service")
    produces: list[ContractDef] = Field(default_factory=list, description="Contracts this service produces")
    consumes: list[str] = Field(default_factory=list, description="Names of contracts this service consumes")


class RepoDef(BaseModel):
    """A source-code repository containing one or more services."""

    name: str = Field(..., description="Repository name (unique)")
    description: str = Field(default="", description="Brief description of the repository")
    services: list[ServiceDef] = Field(default_factory=list, description="Services in this repository")


class TopologyConfig(BaseModel):
    """Root model for the topology YAML file."""

    version: str = Field(default="1", description="Topology format version")
    repositories: list[RepoDef] = Field(default_factory=list, description="Repositories in the topology")


# ---------------------------------------------------------------------------
# Impact analysis models
# ---------------------------------------------------------------------------


class ImpactWarning(BaseModel):
    """A cross-repo impact warning surfaced from the knowledge graph."""

    changed_file: str = Field(..., description="File path that was changed in this PR")
    changed_entity: str = Field(..., description="Name of the contract/schema affected")
    affected_service: str = Field(..., description="Name of the consuming service impacted")
    affected_repository: str = Field(..., description="Repository containing the affected service")
    relationship_type: str = Field(..., description="Type of relationship (e.g. CONSUMES)")
    severity: str = Field(default="medium", description="Impact severity: high, medium, or low")
    description: str = Field(..., description="Human-readable impact description")


class ImpactResult(BaseModel):
    """Aggregated result from a graph impact query."""

    warnings: list[ImpactWarning] = Field(default_factory=list, description="Impact warnings found")
    query_time_ms: float = Field(default=0.0, description="Time taken to execute the graph query in milliseconds")
