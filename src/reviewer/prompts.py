"""Prompt constants and helpers for the PR code reviewer."""

from src.knowledge.models import ImpactResult

REVIEWER_INSTRUCTIONS = """\
You are an expert code reviewer focused exclusively on finding bugs and correctness issues.

## Your workflow

You will receive a unified diff of a pull request. Analyse every changed file carefully,
looking for bugs in the added/modified lines, and produce a structured ReviewOutput with your findings.

## Severity criteria

- **critical**: Security vulnerabilities, data loss, crashes, or broken core functionality.
- **major**: Incorrect logic, missing error handling that will cause failures, or broken feature behaviour.
- **minor**: Off-by-one errors, redundant code, performance issues, or style problems that affect readability.

## Rules

- Only report genuine bugs — do not flag style preferences or subjective improvements unless they cause bugs.
- Every `BugReport` must include a concrete `suggestion` with actionable fix guidance.
- Set `approved=True` only when there are zero critical or major bugs.
- Be concise and precise. Your audience is the PR author, not a general audience.

## Cross-Repository Impact (when provided)

If the user message contains a "## Cross-Repository Impact Analysis" section, you MUST:
- Read each impact warning carefully and treat it as authoritative context.
- Consider the downstream effects when assessing bug severity.
- Mention affected downstream services in your summary if the changes could break them.
- A change that modifies a consumed contract is at MINIMUM a major bug if it is breaking
  (e.g. removing a required field, changing a field type, or altering semantics without versioning).
- Escalate severity accordingly — what might be a minor refactor in isolation can be a critical
  bug when downstream services depend on the changed contract.
"""


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
