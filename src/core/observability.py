"""LLM observability configuration via Opik Cloud.

Single source of truth for Opik initialization and prompt management.
Call ``configure_opik()`` once per process — subsequent calls are no-ops
(idempotent). Mirrors the pattern in ``logging_config.py``.
"""

import functools
import logging
from pathlib import Path
from typing import Any, Callable, TypeVar

from src.core.config import Config

logger = logging.getLogger(__name__)

_configured: bool = False

# Cached prompt text — populated by get_reviewer_prompt() on first call.
_cached_prompt: str | None = None

# Project root: three levels up from this file (src/core/observability.py → repo root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

F = TypeVar("F", bound=Callable[..., Any])


def configure_opik() -> None:
    """Initialize Opik tracing and AgnoInstrumentor. Idempotent.

    No-op when ``Config.OPIK_API_KEY`` is empty — does not import ``opik``
    at all in that case, so the dependency is truly optional at runtime.
    """
    global _configured
    if _configured:
        return

    if not Config.OPIK_API_KEY:
        logger.debug("OPIK_API_KEY not set — Opik observability disabled.")
        _configured = True
        return

    # Lazy imports — only pulled in when Opik is actually enabled.
    import opik
    from openinference.instrumentation.agno import AgnoInstrumentor

    configure_kwargs: dict[str, str] = {
        "api_key": Config.OPIK_API_KEY,
    }
    if Config.OPIK_WORKSPACE:
        configure_kwargs["workspace"] = Config.OPIK_WORKSPACE

    opik.configure(**configure_kwargs)
    AgnoInstrumentor().instrument()

    logger.info(
        "Opik observability enabled (project=%s, workspace=%s)",
        Config.OPIK_PROJECT_NAME,
        Config.OPIK_WORKSPACE or "<default>",
    )
    _configured = True


def get_reviewer_prompt() -> str:
    """Return the reviewer instructions prompt, with caching.

    Resolution order:
    1. If already cached, return the cached value immediately.
    2. If ``OPIK_API_KEY`` is set, try to fetch ``"reviewer_instructions"``
       from the Opik prompt library. On success, cache and return.
    3. On any failure (or if ``OPIK_API_KEY`` is empty), read
       ``prompts/reviewer_instructions.txt`` from the repository root.

    The result is cached for the lifetime of the process — no per-request
    fetches. Restart the process to pick up a new Opik prompt version.
    """
    global _cached_prompt
    if _cached_prompt is not None:
        return _cached_prompt

    prompt_file = _PROJECT_ROOT / "prompts" / "reviewer_instructions.txt"

    if Config.OPIK_API_KEY:
        try:
            import opik

            client = opik.Opik()
            prompt_obj = client.get_prompt(name="reviewer_instructions")
            _cached_prompt = prompt_obj.format()
            logger.info("Loaded reviewer_instructions prompt from Opik library.")
            return _cached_prompt
        except Exception as exc:
            logger.warning(
                "Failed to fetch prompt from Opik — falling back to file: %s",
                exc,
            )

    # Fallback: read from committed file
    _cached_prompt = prompt_file.read_text(encoding="utf-8")
    logger.info("Loaded reviewer_instructions prompt from %s", prompt_file)
    return _cached_prompt


def track_if_enabled(**track_kwargs: Any) -> Callable[[F], F]:
    """Decorator factory: ``@opik.track(...)`` when Opik is configured, identity otherwise.

    Usage::

        @track_if_enabled(name="review_pr")
        def review_pr(owner, repo, pr_number):
            ...

        @track_if_enabled(capture_input=False)
        def review_pr_with_config(owner, repo, pr_number, provider_config, ...):
            ...

    When ``_configured`` is True and ``Config.OPIK_API_KEY`` is non-empty,
    the real ``opik.track`` decorator is applied. Otherwise the function is
    returned unwrapped — zero overhead.

    Note: Because decorators are evaluated at import time but ``configure_opik()``
    runs at startup (lifespan), this decorator defers the decision to call time.
    It wraps the function in a thin shim that checks ``_configured`` on the
    first invocation and then replaces itself with either the traced or
    untraced version for all subsequent calls.
    """

    def decorator(fn: F) -> F:
        # Mutable list used as a cell to hold the resolved function.
        _resolved: list[Callable | None] = [None]

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if _resolved[0] is not None:
                return _resolved[0](*args, **kwargs)

            if _configured and Config.OPIK_API_KEY:
                import opik

                traced_fn = opik.track(**track_kwargs)(fn)
                _resolved[0] = traced_fn
                return traced_fn(*args, **kwargs)
            else:
                _resolved[0] = fn
                return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
