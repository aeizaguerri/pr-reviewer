"""Knowledge graph query functions.

All functions accept a Neo4j driver and return plain dicts or lists.
Query timeout is controlled by ``Config.GRAPH_QUERY_TIMEOUT``.
"""

import logging
import time

from neo4j import Driver
from neo4j.exceptions import ClientError, DriverError, ServiceUnavailable

from src.core.config import Config
from src.knowledge.models import ImpactResult, ImpactWarning
from src.knowledge.schema import (
    CONTRACT,
    CONSUMES,
    DEFINES,
    OWNS,
    PRODUCES,
    REPOSITORY,
    SCHEMA,
    SERVICE,
)

logger = logging.getLogger(__name__)


def _run_query(
    driver: Driver,
    cypher: str,
    parameters: dict | None = None,
    timeout: int | None = None,
) -> list[dict]:
    """Execute a read query with the configured timeout.

    Args:
        driver: An active Neo4j driver instance.
        cypher: The Cypher query string.
        parameters: Query parameters dict (optional).
        timeout: Override for the query timeout in seconds. Defaults to
            ``Config.GRAPH_QUERY_TIMEOUT`` when not supplied.
    """
    effective_timeout = timeout if timeout is not None else Config.GRAPH_QUERY_TIMEOUT
    with driver.session() as session:
        result = session.run(cypher, parameters or {}, timeout=effective_timeout)
        return [record.data() for record in result]


def find_consumers(driver: Driver, contract_name: str) -> list[dict]:
    """Finds all services/repos that CONSUME a given contract.

    Returns a list of dicts with keys: service, repository.
    """
    cypher = (
        f"MATCH (s:{SERVICE})-[:{CONSUMES}]->(c:{CONTRACT} {{name: $name}}) "
        f"OPTIONAL MATCH (r:{REPOSITORY})-[:{OWNS}]->(s) "
        f"RETURN s.name AS service, r.name AS repository "
        f"ORDER BY s.name"
    )
    return _run_query(driver, cypher, {"name": contract_name})


def find_producers(driver: Driver, contract_name: str) -> list[dict]:
    """Finds all services/repos that PRODUCE a given contract.

    Returns a list of dicts with keys: service, repository.
    """
    cypher = (
        f"MATCH (s:{SERVICE})-[:{PRODUCES}]->(c:{CONTRACT} {{name: $name}}) "
        f"OPTIONAL MATCH (r:{REPOSITORY})-[:{OWNS}]->(s) "
        f"RETURN s.name AS service, r.name AS repository "
        f"ORDER BY s.name"
    )
    return _run_query(driver, cypher, {"name": contract_name})


def find_impact_by_path(driver: Driver, file_path: str) -> list[dict]:
    """Given a file path, finds the schema/contract it belongs to, then
    finds all consumers of that entity's contract.

    Returns a list of dicts with keys: entity_name, entity_type, consumers.
    """
    # Match contracts by file_path
    cypher_contract = (
        f"MATCH (c:{CONTRACT} {{file_path: $path}})<-[:{CONSUMES}]-(s:{SERVICE}) "
        f"RETURN c.name AS entity_name, '{CONTRACT}' AS entity_type, "
        f"collect(DISTINCT s.name) AS consumers"
    )

    # Match schemas by file_path, then traverse to their contract's consumers
    cypher_schema = (
        f"MATCH (sc:{SCHEMA} {{file_path: $path}})<-[:{DEFINES}]-(c:{CONTRACT})"
        f"<-[:{CONSUMES}]-(s:{SERVICE}) "
        f"RETURN sc.name AS entity_name, '{SCHEMA}' AS entity_type, "
        f"collect(DISTINCT s.name) AS consumers"
    )

    results = []
    for cypher in [cypher_contract, cypher_schema]:
        rows = _run_query(driver, cypher, {"path": file_path})
        results.extend(rows)

    return results


def find_consumers_of_paths(
    driver: Driver,
    file_paths: list[str],
    timeout: int = 5,
) -> ImpactResult:
    """Given a list of changed file paths from a PR diff, finds all downstream consumers.

    For each path: finds the Contract/Schema node with that file_path → finds all
    Services that CONSUME that contract → finds the Repository that OWNS each service.

    Caps results at ``Config.MAX_IMPACT_WARNINGS``. Handles Neo4j unavailability
    gracefully — returns an empty ``ImpactResult`` on any error.

    Args:
        driver: An active Neo4j driver instance.
        file_paths: List of file paths extracted from the PR diff.
        timeout: Query timeout in seconds (overrides Config default if provided).

    Returns:
        An ``ImpactResult`` containing ``ImpactWarning`` objects and query_time_ms.
    """
    if not file_paths:
        return ImpactResult()

    start = time.monotonic()

    try:
        # Query contracts by file_path
        cypher_contract = (
            f"UNWIND $paths AS path "
            f"MATCH (c:{CONTRACT} {{file_path: path}})<-[:{CONSUMES}]-(s:{SERVICE}) "
            f"OPTIONAL MATCH (r:{REPOSITORY})-[:{OWNS}]->(s) "
            f"RETURN path AS changed_file, "
            f"       c.name AS changed_entity, "
            f"       '{CONTRACT}' AS entity_type, "
            f"       s.name AS affected_service, "
            f"       r.name AS affected_repository "
            f"ORDER BY changed_file, changed_entity, affected_service"
        )

        # Query schemas by file_path → traverse to their contract's consumers
        cypher_schema = (
            f"UNWIND $paths AS path "
            f"MATCH (sc:{SCHEMA} {{file_path: path}})<-[:{DEFINES}]-(c:{CONTRACT})"
            f"<-[:{CONSUMES}]-(s:{SERVICE}) "
            f"OPTIONAL MATCH (r:{REPOSITORY})-[:{OWNS}]->(s) "
            f"RETURN path AS changed_file, "
            f"       sc.name AS changed_entity, "
            f"       '{SCHEMA}' AS entity_type, "
            f"       s.name AS affected_service, "
            f"       r.name AS affected_repository "
            f"ORDER BY changed_file, changed_entity, affected_service"
        )

        rows: list[dict] = []
        for cypher in [cypher_contract, cypher_schema]:
            rows.extend(_run_query(driver, cypher, {"paths": file_paths}, timeout=timeout))

        query_time_ms = (time.monotonic() - start) * 1000
        max_warnings = Config.MAX_IMPACT_WARNINGS
        truncated = len(rows) > max_warnings
        rows = rows[:max_warnings]

        warnings: list[ImpactWarning] = []
        for row in rows:
            entity_type = row.get("entity_type", "Contract")
            changed_entity = row.get("changed_entity") or ""
            affected_service = row.get("affected_service") or "unknown-service"
            affected_repository = row.get("affected_repository") or "unknown-repository"
            changed_file = row.get("changed_file") or ""

            description = (
                f"`{affected_service}` (in `{affected_repository}`) "
                f"consumes {entity_type.lower()} `{changed_entity}` "
                f"defined at `{changed_file}`."
            )

            warnings.append(
                ImpactWarning(
                    changed_file=changed_file,
                    changed_entity=changed_entity,
                    affected_service=affected_service,
                    affected_repository=affected_repository,
                    relationship_type=CONSUMES,
                    severity="medium",
                    description=description,
                )
            )

        if truncated:
            logger.warning(
                "Impact analysis capped at %d warnings (more results exist).",
                max_warnings,
            )

        return ImpactResult(warnings=warnings, query_time_ms=query_time_ms)

    except (ServiceUnavailable, DriverError, ClientError) as exc:
        query_time_ms = (time.monotonic() - start) * 1000
        logger.warning("Graph impact query failed (Neo4j error): %s", exc)
        return ImpactResult(query_time_ms=query_time_ms)
    except Exception as exc:
        query_time_ms = (time.monotonic() - start) * 1000
        logger.warning("Graph impact query failed (unexpected error): %s", exc)
        return ImpactResult(query_time_ms=query_time_ms)


def find_all_consumers(driver: Driver, contract_name: str) -> list[str]:
    """Returns all service names that CONSUME the given contract. Used by CLI.

    Args:
        driver: An active Neo4j driver instance.
        contract_name: The contract name to look up.

    Returns:
        A list of service names (may be empty).
    """
    rows = find_consumers(driver, contract_name)
    return [r["service"] for r in rows if r.get("service")]


def find_entity_by_name(driver: Driver, name: str) -> dict | None:
    """Looks up a single entity (Contract or Schema) by name. Used by CLI.

    Returns a dict with keys: name, label, file_path, producers, consumers.
    Returns None if the entity is not found.

    Args:
        driver: An active Neo4j driver instance.
        name: The entity name to look up.
    """
    cypher = (
        f"OPTIONAL MATCH (c:{CONTRACT} {{name: $name}}) "
        f"OPTIONAL MATCH (sc:{SCHEMA} {{name: $name}}) "
        f"RETURN c.name AS contract_name, c.file_path AS contract_file, "
        f"       sc.name AS schema_name, sc.file_path AS schema_file"
    )
    rows = _run_query(driver, cypher, {"name": name})
    if not rows:
        return None

    row = rows[0]
    if row.get("contract_name"):
        producers = find_producers(driver, name)
        consumers = find_consumers(driver, name)
        return {
            "name": row["contract_name"],
            "label": CONTRACT,
            "file_path": row.get("contract_file") or "",
            "producers": [r["service"] for r in producers],
            "consumers": [r["service"] for r in consumers],
        }
    if row.get("schema_name"):
        return {
            "name": row["schema_name"],
            "label": SCHEMA,
            "file_path": row.get("schema_file") or "",
            "producers": [],
            "consumers": [],
        }
    return None


def search_entities(driver: Driver, query: str) -> list[dict]:
    """General search across all node types by name (case-insensitive contains).

    Returns a list of dicts with keys: label, name, description (optional).
    """
    cypher = (
        f"CALL {{ "
        f"  MATCH (n:{REPOSITORY}) WHERE toLower(n.name) CONTAINS toLower($query) "
        f"  RETURN labels(n)[0] AS label, n.name AS name, n.description AS description "
        f"  UNION "
        f"  MATCH (n:{SERVICE}) WHERE toLower(n.name) CONTAINS toLower($query) "
        f"  RETURN labels(n)[0] AS label, n.name AS name, n.description AS description "
        f"  UNION "
        f"  MATCH (n:{CONTRACT}) WHERE toLower(n.name) CONTAINS toLower($query) "
        f"  RETURN labels(n)[0] AS label, n.name AS name, n.description AS description "
        f"  UNION "
        f"  MATCH (n:{SCHEMA}) WHERE toLower(n.name) CONTAINS toLower($query) "
        f"  RETURN labels(n)[0] AS label, n.name AS name, n.description AS description "
        f"}} "
        f"RETURN label, name, description "
        f"ORDER BY label, name"
    )
    return _run_query(driver, cypher, {"query": query})
