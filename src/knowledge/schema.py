"""Graph schema definitions: node labels, relationship types, constraints, and indexes.

All Cypher DDL uses ``IF NOT EXISTS`` so that ``init_schema()`` is fully idempotent.
"""

import logging

from neo4j import Driver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Node label constants
# ---------------------------------------------------------------------------
REPOSITORY = "Repository"
SERVICE = "Service"
CONTRACT = "Contract"
SCHEMA = "Schema"
FIELD = "Field"

# ---------------------------------------------------------------------------
# Relationship type constants
# ---------------------------------------------------------------------------
OWNS = "OWNS"
PRODUCES = "PRODUCES"
CONSUMES = "CONSUMES"
DEFINES = "DEFINES"
HAS_FIELD = "HAS_FIELD"

# ---------------------------------------------------------------------------
# Uniqueness constraints
# ---------------------------------------------------------------------------
CONSTRAINTS: list[str] = [
    f"CREATE CONSTRAINT repo_name IF NOT EXISTS FOR (r:{REPOSITORY}) REQUIRE r.name IS UNIQUE",
    f"CREATE CONSTRAINT service_name IF NOT EXISTS FOR (s:{SERVICE}) REQUIRE s.name IS UNIQUE",
    f"CREATE CONSTRAINT contract_name IF NOT EXISTS FOR (c:{CONTRACT}) REQUIRE c.name IS UNIQUE",
    f"CREATE CONSTRAINT schema_name IF NOT EXISTS FOR (sc:{SCHEMA}) REQUIRE sc.name IS UNIQUE",
]

# ---------------------------------------------------------------------------
# Lookup indexes (for file-path matching during review)
# ---------------------------------------------------------------------------
INDEXES: list[str] = [
    f"CREATE INDEX contract_file_path IF NOT EXISTS FOR (c:{CONTRACT}) ON (c.file_path)",
    f"CREATE INDEX schema_file_path IF NOT EXISTS FOR (sc:{SCHEMA}) ON (sc.file_path)",
]


def init_schema(driver: Driver) -> None:
    """Creates all constraints and indexes in Neo4j. Idempotent.

    Args:
        driver: An active Neo4j driver instance.
    """
    with driver.session() as session:
        for cypher in CONSTRAINTS:
            session.run(cypher)
            logger.info("Executed: %s", cypher)

        for cypher in INDEXES:
            session.run(cypher)
            logger.info("Executed: %s", cypher)
