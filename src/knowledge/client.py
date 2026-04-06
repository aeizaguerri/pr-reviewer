"""Neo4j driver singleton wrapper with lazy initialization and health checks."""

import logging
import time

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

_health_cache: tuple[bool, float] | None = None
_HEALTH_CACHE_TTL = 30


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
            max_connection_lifetime=3600,
            max_connection_pool_size=50,
            connection_acquisition_timeout=60,
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
    """Verifies Neo4j connectivity with caching. Returns True if reachable, False otherwise.

    Uses a TTL cache to distinguish repeated failures from "not configured".
    Never raises — all exceptions are caught and logged.
    """
    global _health_cache

    now = time.monotonic()
    if _health_cache is not None:
        cached_result, cached_time = _health_cache
        if now - cached_time < _HEALTH_CACHE_TTL:
            return cached_result

    try:
        driver = get_driver()
        driver.verify_connectivity()
        _health_cache = (True, now)
        return True
    except (GraphError, ServiceUnavailable, DriverError, ClientError, OSError) as exc:
        logger.warning("Neo4j health check failed: %s", exc)
        _health_cache = (False, now)
        return False
    except Exception as exc:
        logger.warning("Unexpected error during Neo4j health check: %s", exc)
        _health_cache = (False, now)
        return False
