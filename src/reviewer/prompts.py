"""Prompt constants and helpers for the PR code reviewer."""

from src.knowledge.models import ImpactResult
from src.core.observability import get_reviewer_prompt

# Type annotation for static analysis — value is loaded lazily via __getattr__.
REVIEWER_INSTRUCTIONS: str


def __getattr__(name: str) -> str:
    if name == "REVIEWER_INSTRUCTIONS":
        value = get_reviewer_prompt()
        globals()["REVIEWER_INSTRUCTIONS"] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _build_impact_section(impact_result: ImpactResult) -> str:
    """Builds a markdown-formatted section to inject into the review prompt.

    Returns an empty string if there are no warnings.

    Args:
        impact_result: The result from ``find_consumers_of_paths()``.

    Returns:
        A formatted markdown string ready for prompt injection, or ``""`` if no warnings.
    """
    warnings = impact_result.warnings
    if not warnings:
        return ""

    lines: list[str] = [
        "## Cross-Repository Impact Analysis",
        "",
        "The following changes may affect downstream services:",
        "",
    ]

    for w in warnings:
        severity_badge = w.severity.upper()
        lines.append(
            f"- **{w.affected_service}** (in `{w.affected_repository}`): "
            f"`{w.changed_file}` affects `{w.changed_entity}` [{severity_badge}]"
        )
        lines.append(f"  {w.description}")
        lines.append("")

    lines.append("Please consider these downstream impacts in your review.")

    return "\n".join(lines)
