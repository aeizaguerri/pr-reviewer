"""Prompt constants and helpers for the PR code reviewer."""

from src.knowledge.models import ImpactResult
from src.core.observability import get_reviewer_prompt

# Type annotations for static analysis — values are loaded lazily via __getattr__.
REVIEWER_INSTRUCTIONS: str
BUG_REVIEWER_INSTRUCTIONS: str
SECURITY_REVIEWER_INSTRUCTIONS: str
CROSS_REPO_IMPACT_REVIEWER_INSTRUCTIONS: str
JUDGE_INSTRUCTIONS: str


def __getattr__(name: str) -> str:
    if name == "REVIEWER_INSTRUCTIONS":
        value = get_reviewer_prompt()
        globals()["REVIEWER_INSTRUCTIONS"] = value
        return value

    if name == "BUG_REVIEWER_INSTRUCTIONS":
        value = (
            "You are a code defect reviewer. Your job is to find bugs in the provided diff. "
            "Focus on correctness, logic errors, type mismatches, null-pointer risks, "
            "off-by-one errors, and regressions. "
            "Do NOT report security vulnerabilities or cross-repository impact. "
            "Output a JSON object matching the SpecialistBugOutput schema."
        )
        globals()["BUG_REVIEWER_INSTRUCTIONS"] = value
        return value

    if name == "SECURITY_REVIEWER_INSTRUCTIONS":
        value = (
            "You are a security reviewer. Your job is to identify CWE-style vulnerabilities "
            "such as injection, broken authentication, sensitive data exposure, SSRF, "
            "path traversal, and insecure deserialization. "
            "Do NOT report general bugs or cross-repository impact. "
            "Output a JSON object matching the SpecialistSecurityOutput schema."
        )
        globals()["SECURITY_REVIEWER_INSTRUCTIONS"] = value
        return value

    if name == "CROSS_REPO_IMPACT_REVIEWER_INSTRUCTIONS":
        value = (
            "You are a cross-repository impact reviewer. Your job is to assess whether "
            "the changed files affect downstream services based ONLY on the evidence "
            "provided in the impact analysis section. "
            "If no impact evidence is present, return an empty impact_warnings list. "
            "Do NOT invent impact warnings. "
            "Output a JSON object matching the SpecialistImpactOutput schema."
        )
        globals()["CROSS_REPO_IMPACT_REVIEWER_INSTRUCTIONS"] = value
        return value

    if name == "JUDGE_INSTRUCTIONS":
        value = (
            "You are a judge. Compare bug findings from Reviewer A and Reviewer B. "
            "Deduplicate by (file, line, severity, description). Escalate severity on conflict. "
            "Return a JSON array of deduplicated BugReport-shaped objects."
        )
        globals()["JUDGE_INSTRUCTIONS"] = value
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
