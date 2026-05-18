"""LLM observability configuration via Opik Cloud.

Single source of truth for Opik initialization and prompt management.
Call ``configure_opik()`` once per process — subsequent calls are no-ops
(idempotent). Mirrors the pattern in ``logging_config.py``.
"""

import functools
import logging
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Callable, TypeVar

from src.core.config import Config

logger = logging.getLogger(__name__)

_configured: bool = False

ACTIVE_PROMPT_NAMES: tuple[str, ...] = (
    "bug_reviewer_instructions",
    "security_reviewer_instructions",
    "cross_repo_impact_reviewer_instructions",
    "bug_review_team_leader",
    "pr_review_prompt",
)

_TEMPLATE_VARIABLES: dict[str, set[str]] = {
    "bug_review_team_leader": {"shared_prompt"},
    "pr_review_prompt": {"pr_title", "diff_text"},
}

# Cached prompt text, keyed by Opik prompt name.
_prompt_cache: dict[str, str] = {}

_fallback_mode_logged: bool = False

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


def _fallback_path(name: str) -> Path:
    return _PROJECT_ROOT / "prompts" / f"{name}.txt"


def _load_prompt_from_file(name: str) -> str:
    prompt_file = _fallback_path(name)
    value = prompt_file.read_text(encoding="utf-8")
    logger.info("Loaded %s prompt from %s", name, prompt_file)
    return value


def _load_prompt_from_opik(name: str) -> str:
    import opik

    client = opik.Opik()
    prompt_obj = client.get_prompt(name=name)
    raw_template = getattr(prompt_obj, "_template", None)
    if isinstance(raw_template, str):
        return raw_template
    return prompt_obj.format()


def get_prompt(name: str) -> str:
    """Return a prompt by snake_case name, using Opik first and local fallback.

    Prompt text is cached per prompt name for the lifetime of the process.
    Opik is imported only when ``OPIK_API_KEY`` is configured.
    """
    if name in _prompt_cache:
        return _prompt_cache[name]

    if Config.OPIK_API_KEY:
        try:
            value = _load_prompt_from_opik(name)
            _prompt_cache[name] = value
            logger.info("Loaded %s prompt from Opik library.", name)
            return value
        except Exception as exc:
            logger.warning(
                "Failed to fetch Opik prompt %s (%s); using local fallback.",
                name,
                type(exc).__name__,
            )

    value = _load_prompt_from_file(name)
    _prompt_cache[name] = value
    return value


_PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def render_prompt(name: str, **variables: str) -> str:
    """Render a named prompt template with only registry-approved variables.

    Prompt bodies may include literal braces for JSON examples. Replace only
    simple placeholders registered for this prompt and leave all other braces as
    prompt text instead of treating the whole template as a Python format string.
    """
    allowed = _TEMPLATE_VARIABLES.get(name, set())
    safe_variables = {key: variables[key] for key in allowed if key in variables}

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in safe_variables:
            return match.group(0)
        return safe_variables[key]

    return _PLACEHOLDER_PATTERN.sub(replace, get_prompt(name))


def warm_prompt_cache(names: Iterable[str]) -> None:
    """Best-effort startup warmup for named prompts.

    Failures are handled by ``get_prompt`` through local fallback. Missing fallback
    files are logged and do not prevent application startup.
    """
    global _fallback_mode_logged
    if not Config.OPIK_API_KEY and not _fallback_mode_logged:
        logger.warning("Opik prompt retrieval unavailable; using local fallback prompts.")
        _fallback_mode_logged = True

    for name in names:
        try:
            get_prompt(name)
        except Exception as exc:
            logger.warning(
                "Prompt warmup failed for %s (%s); startup will continue.",
                name,
                type(exc).__name__,
            )


def get_reviewer_prompt() -> str:
    """Compatibility wrapper for the legacy reviewer instructions prompt."""
    return get_prompt("reviewer_instructions")


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
