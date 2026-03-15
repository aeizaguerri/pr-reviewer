"""Knowledge graph module for cross-repo impact detection.

Provides a Neo4j-backed knowledge graph that stores inter-service dependency
relationships (repositories, services, contracts, schemas) and surfaces
cross-repo impact warnings during PR reviews.

Public API
----------
Driver management::

    from src.knowledge import get_driver, close_driver, check_health

Schema initialisation::

    from src.knowledge import init_schema

Topology population::

    from src.knowledge import load_topology, populate_graph

Impact queries::

    from src.knowledge import find_consumers_of_paths, find_all_consumers, find_entity_by_name

Models::

    from src.knowledge import ImpactWarning, ImpactResult, TopologyConfig
"""

from src.knowledge.client import check_health, close_driver, get_driver
from src.knowledge.models import ImpactResult, ImpactWarning, TopologyConfig
from src.knowledge.population import load_topology, populate_graph
from src.knowledge.queries import (
    find_all_consumers,
    find_consumers_of_paths,
    find_entity_by_name,
)
from src.knowledge.schema import init_schema

__all__ = [
    # Client
    "get_driver",
    "close_driver",
    "check_health",
    # Schema
    "init_schema",
    # Models
    "ImpactWarning",
    "ImpactResult",
    "TopologyConfig",
    # Population
    "load_topology",
    "populate_graph",
    # Queries
    "find_consumers_of_paths",
    "find_all_consumers",
    "find_entity_by_name",
]
