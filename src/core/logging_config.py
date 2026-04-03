"""Centralized logging configuration for pr-reviewer.

Single source of truth for all logging setup across CLI, FastAPI, and Streamlit
entrypoints. Call ``configure_logging()`` once per process — subsequent calls are
no-ops (idempotent).
"""

import logging
import logging.config
import warnings

_configured: bool = False

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

_THIRD_PARTY_LOGGERS = [
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
    "httpx",
    "agno",
    "neo4j",
    "neo4j.io",
]


def configure_logging(level: str = "INFO") -> None:
    """Apply centralized logging configuration. Idempotent — second call is a no-op.

    Args:
        level: Desired log level for application loggers (``src.*`` and
            ``backend.*``). When the caller passes the default ``"INFO"``, the
            value of the ``LOG_LEVEL`` environment variable is used instead
            (falling back to ``"INFO"`` if unset). Explicit non-default values
            override the environment variable, which lets the CLI ``--debug``
            flag force ``"DEBUG"`` unconditionally.

    Invalid values fall back to ``"INFO"`` with a :func:`warnings.warn`
    notification (the logger is not yet configured at that point, so we cannot
    use it).
    """
    global _configured
    if _configured:
        return

    # Resolve effective level: explicit param wins over env var.
    if level == "INFO":
        # Only read env var when caller did not override explicitly.
        from src.core.config import Config  # local import to avoid circular deps

        effective = Config.LOG_LEVEL
    else:
        effective = level

    effective = effective.upper().strip()

    if effective not in _VALID_LEVELS:
        warnings.warn(
            f"Invalid LOG_LEVEL={effective!r}, falling back to INFO",
            stacklevel=2,
        )
        effective = "INFO"

    # Build third-party logger entries — all pinned to WARNING.
    tp_loggers: dict = {
        name: {
            "level": "WARNING",
            "handlers": ["console"],
            "propagate": False,
        }
        for name in _THIRD_PARTY_LOGGERS
    }

    config: dict = {
        "version": 1,
        # CRITICAL: must be False so that loggers created at import-time
        # (before configure_logging runs) are not silenced by dictConfig.
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": (
                    "%(asctime)s [%(levelname)s] %(name)s"
                    " (%(filename)s:%(lineno)d): %(message)s"
                ),
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                # ext:// prefix tells dictConfig to resolve the object reference.
                "stream": "ext://sys.stdout",
                "formatter": "standard",
            },
        },
        "loggers": {
            "src": {
                "level": effective,
                "handlers": ["console"],
                "propagate": False,
            },
            "backend": {
                "level": effective,
                "handlers": ["console"],
                "propagate": False,
            },
            **tp_loggers,
        },
        "root": {
            "level": "WARNING",
            "handlers": ["console"],
        },
    }

    logging.config.dictConfig(config)
    _configured = True
