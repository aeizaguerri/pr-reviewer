"""Pytest fixtures for the knowledge test suite."""

from pathlib import Path

import pytest

from src.knowledge.models import ImpactResult, ImpactWarning


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


@pytest.fixture
def topology_yaml_path() -> Path:
    """Returns the path to examples/topology.yaml (real file, no Neo4j needed)."""
    base = Path(__file__).parent.parent.parent.parent
    return base / "examples" / "topology.yaml"
