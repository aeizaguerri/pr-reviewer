"""YAML topology parser and Neo4j graph population.

Reads a YAML file describing the service topology, validates it with Pydantic,
and populates the Neo4j knowledge graph using idempotent MERGE operations
within a single transaction.
"""

import logging
from pathlib import Path

import yaml
from neo4j import Driver, ManagedTransaction

from src.knowledge.models import TopologyConfig
from src.knowledge.schema import (
    CONSUMES,
    CONTRACT,
    DEFINES,
    FIELD,
    HAS_FIELD,
    OWNS,
    PRODUCES,
    REPOSITORY,
    SCHEMA,
    SERVICE,
)

logger = logging.getLogger(__name__)


def load_topology(yaml_path: str | Path) -> TopologyConfig:
    """Reads and validates a YAML topology file.

    Args:
        yaml_path: Path to the YAML file.

    Returns:
        A validated TopologyConfig instance.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
        pydantic.ValidationError: If the content fails Pydantic validation.
    """
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Topology file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raw = {}

    topology = TopologyConfig.model_validate(raw)
    logger.info("Loaded topology: %d repositories", len(topology.repositories))
    return topology


def _populate_tx(tx: ManagedTransaction, topology: TopologyConfig) -> dict:
    """Runs all MERGE operations inside a single managed transaction.

    Returns a stats dict with nodes_created and relationships_created counts.
    """
    nodes_created = 0
    relationships_created = 0

    for repo_def in topology.repositories:
        # MERGE Repository
        tx.run(
            f"MERGE (r:{REPOSITORY} {{name: $name}}) "
            f"SET r.description = $description",
            name=repo_def.name,
            description=repo_def.description,
        )
        nodes_created += 1

        for svc_def in repo_def.services:
            # MERGE Service + OWNS relationship
            tx.run(
                f"MERGE (s:{SERVICE} {{name: $svc_name}}) "
                f"SET s.description = $description "
                f"WITH s "
                f"MATCH (r:{REPOSITORY} {{name: $repo_name}}) "
                f"MERGE (r)-[:{OWNS}]->(s)",
                svc_name=svc_def.name,
                description=svc_def.description,
                repo_name=repo_def.name,
            )
            nodes_created += 1
            relationships_created += 1

            # Produced contracts
            for contract_def in svc_def.produces:
                # MERGE Contract + PRODUCES relationship
                tx.run(
                    f"MERGE (c:{CONTRACT} {{name: $contract_name}}) "
                    f"SET c.file_path = $file_path, c.type = $type "
                    f"WITH c "
                    f"MATCH (s:{SERVICE} {{name: $svc_name}}) "
                    f"MERGE (s)-[:{PRODUCES}]->(c)",
                    contract_name=contract_def.name,
                    file_path=contract_def.file_path,
                    type=contract_def.type,
                    svc_name=svc_def.name,
                )
                nodes_created += 1
                relationships_created += 1

                # Schemas under this contract
                for schema_def in contract_def.schemas:
                    # MERGE Schema + DEFINES relationship
                    tx.run(
                        f"MERGE (sc:{SCHEMA} {{name: $schema_name}}) "
                        f"SET sc.file_path = $file_path "
                        f"WITH sc "
                        f"MATCH (c:{CONTRACT} {{name: $contract_name}}) "
                        f"MERGE (c)-[:{DEFINES}]->(sc)",
                        schema_name=schema_def.name,
                        file_path=schema_def.file_path,
                        contract_name=contract_def.name,
                    )
                    nodes_created += 1
                    relationships_created += 1

                    # Fields under this schema
                    for field_def in schema_def.fields:
                        # MERGE Field + HAS_FIELD relationship
                        # Use schema-scoped name for uniqueness
                        field_key = f"{schema_def.name}.{field_def.name}"
                        tx.run(
                            f"MERGE (f:{FIELD} {{name: $field_key}}) "
                            f"SET f.field_name = $field_name, f.type = $type, f.required = $required "
                            f"WITH f "
                            f"MATCH (sc:{SCHEMA} {{name: $schema_name}}) "
                            f"MERGE (sc)-[:{HAS_FIELD}]->(f)",
                            field_key=field_key,
                            field_name=field_def.name,
                            type=field_def.type,
                            required=field_def.required,
                            schema_name=schema_def.name,
                        )
                        nodes_created += 1
                        relationships_created += 1

            # Consumed contracts (reference by name)
            for contract_name in svc_def.consumes:
                tx.run(
                    f"MERGE (c:{CONTRACT} {{name: $contract_name}}) "
                    f"WITH c "
                    f"MATCH (s:{SERVICE} {{name: $svc_name}}) "
                    f"MERGE (s)-[:{CONSUMES}]->(c)",
                    contract_name=contract_name,
                    svc_name=svc_def.name,
                )
                relationships_created += 1

    return {
        "nodes_created": nodes_created,
        "relationships_created": relationships_created,
    }


def populate_graph(driver: Driver, topology: TopologyConfig) -> dict:
    """Populates the Neo4j knowledge graph from a TopologyConfig.

    Uses MERGE for all operations (idempotent). Runs in a single transaction
    for atomicity — if any operation fails, the entire import is rolled back.

    Args:
        driver: An active Neo4j driver instance.
        topology: A validated TopologyConfig.

    Returns:
        Summary dict with keys ``nodes_created`` and ``relationships_created``.
    """
    with driver.session() as session:
        stats = session.execute_write(lambda tx: _populate_tx(tx, topology))

    logger.info(
        "Graph populated: %d nodes, %d relationships",
        stats["nodes_created"],
        stats["relationships_created"],
    )
    return stats
