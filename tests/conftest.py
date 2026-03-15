"""Shared pytest fixtures for the PR Code Reviewer test suite."""

import os
from pathlib import Path

import pytest

from src.knowledge.models import ImpactResult, ImpactWarning


# ---------------------------------------------------------------------------
# Fixtures: sample diff text
# ---------------------------------------------------------------------------

SAMPLE_DIFF = """\
### src/contracts/order_created.py
@@ -1,5 +1,6 @@
-order_id: str
+order_id: int
 customer_email: str
 total_amount: float

### src/schemas/order_created_payload.py
@@ -10,3 +10,4 @@
 items: list
+metadata: dict
"""

SAMPLE_DIFF_DUPLICATES = """\
### src/contracts/order_created.py
@@ -1,5 +1,6 @@
 some content

### src/contracts/order_created.py
@@ -10,3 +10,4 @@
 more content
"""

EMPTY_DIFF = ""


@pytest.fixture
def sample_diff() -> str:
    """A minimal diff with two different files."""
    return SAMPLE_DIFF


@pytest.fixture
def sample_diff_duplicates() -> str:
    """A diff where the same file appears twice."""
    return SAMPLE_DIFF_DUPLICATES


@pytest.fixture
def empty_diff() -> str:
    return EMPTY_DIFF


# ---------------------------------------------------------------------------
# Fixtures: ImpactWarning / ImpactResult
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_warning() -> ImpactWarning:
    return ImpactWarning(
        changed_file="src/contracts/order_created.py",
        changed_entity="OrderCreatedEvent",
        affected_service="payment-worker",
        affected_repository="payment-service",
        relationship_type="CONSUMES",
        severity="medium",
        description="`payment-worker` (in `payment-service`) consumes contract `OrderCreatedEvent`.",
    )


@pytest.fixture
def sample_impact_result(sample_warning: ImpactWarning) -> ImpactResult:
    return ImpactResult(warnings=[sample_warning], query_time_ms=12.5)


@pytest.fixture
def empty_impact_result() -> ImpactResult:
    return ImpactResult()


# ---------------------------------------------------------------------------
# Fixtures: sample topology YAML path
# ---------------------------------------------------------------------------

@pytest.fixture
def topology_yaml_path() -> Path:
    """Returns the path to examples/topology.yaml (real file, no Neo4j needed)."""
    base = Path(__file__).parent.parent
    return base / "examples" / "topology.yaml"


# ---------------------------------------------------------------------------
# Fixtures: environment variable helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def graph_enrichment_enabled(monkeypatch):
    """Sets ENABLE_GRAPH_ENRICHMENT=true for the duration of the test."""
    monkeypatch.setenv("ENABLE_GRAPH_ENRICHMENT", "true")
    # Force Config to reload (class attributes are evaluated at import time;
    # we patch the attribute directly on the class for simplicity)
    import src.core.config as cfg_module
    monkeypatch.setattr(cfg_module.Config, "ENABLE_GRAPH_ENRICHMENT", True)


@pytest.fixture
def graph_enrichment_disabled(monkeypatch):
    """Sets ENABLE_GRAPH_ENRICHMENT=false for the duration of the test."""
    monkeypatch.setenv("ENABLE_GRAPH_ENRICHMENT", "false")
    import src.core.config as cfg_module
    monkeypatch.setattr(cfg_module.Config, "ENABLE_GRAPH_ENRICHMENT", False)
