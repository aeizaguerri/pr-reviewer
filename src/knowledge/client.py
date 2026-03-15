"""Neo4j driver singleton wrapper with lazy initialization and health checks."""

import logging

from neo4j import Driver, GraphDatabase
from neo4j.exceptions import (
    AuthError,
    ClientError,
    DriverError,
    ServiceUnavailable,
)

from src.core.config import Config
from src.core.exceptions import GraphError

logger = logging.getLogger(__name__)

_driver: Driver | None = None


def get_driver() -> Driver:
    """Returns the singleton Neo4j driver, creating it on first call.

    Raises:
        GraphError: If the driver cannot be created (bad URI, auth failure, etc.).
    """
    global _driver
    if _driver is not None:
        return _driver

    try:
        _driver = GraphDatabase.driver(
            Config.NEO4J_URI,
            auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD),
        )
        return _driver
    except (DriverError, AuthError) as exc:
        raise GraphError(f"Failed to create Neo4j driver: {exc}") from exc


def close_driver() -> None:
    """Closes the Neo4j driver connection pool if open."""
    global _driver
    if _driver is not None:
        try:
            _driver.close()
        except DriverError:
            logger.warning("Error closing Neo4j driver", exc_info=True)
        finally:
            _driver = None


def check_health() -> bool:
    """Verifies Neo4j connectivity. Returns True if reachable, False otherwise.

    Never raises — all exceptions are caught and logged.
    """
    try:
        driver = get_driver()
        driver.verify_connectivity()
        return True
    except (GraphError, ServiceUnavailable, DriverError, ClientError, OSError) as exc:
        logger.warning("Neo4j health check failed: %s", exc)
        return False
    except Exception as exc:
        logger.warning("Unexpected error during Neo4j health check: %s", exc)
        return False
