"""Pure helper functions for Streamlit grouped rendering.

These functions have no Streamlit dependency and can be unit-tested
independently of the UI framework.
"""


def group_findings_by_category(bugs: list[dict]) -> dict[str, list[dict]]:
    """Group bug findings by category, defaulting missing category to 'bug'."""
    groups: dict[str, list[dict]] = {}
    for bug in bugs:
        category = bug.get("category", "bug") or "bug"
        groups.setdefault(category, []).append(bug)
    return groups


def format_bug_row(bug: dict) -> dict:
    """Format a single bug dict into a display row dict."""
    severity_emoji = {"critical": "🔴", "major": "🟠", "minor": "🟡"}
    sev = bug.get("severity", "")
    return {
        "Severity": f"{severity_emoji.get(sev, '')} {sev}".strip(),
        "File": bug.get("file", ""),
        "Line": bug.get("line", 0),
        "Description": bug.get("description", ""),
        "Suggestion": bug.get("suggestion", ""),
    }


def format_review_health(health: dict | None) -> dict | None:
    """Normalize review health dict for display, or None if absent."""
    if health is None:
        return None
    return {
        "status": health.get("status", "complete"),
        "warnings": list(health.get("warnings", [])),
    }


def build_review_display(result: dict) -> dict:
    """Build a pure display model from a backend review result dict.

    This function extracts and formats all data needed by the UI render path
    without any Streamlit dependency, making it fully unit-testable.
    """
    approved = result.get("approved", False)
    bugs = result.get("bugs", [])
    grouped = group_findings_by_category(bugs)
    bug_items = grouped.get("bug", [])
    security_items = grouped.get("security", [])

    return {
        "approved": approved,
        "approval_label": "✅ Approved" if approved else "❌ Changes Requested",
        "approval_delta": "Ready to merge" if approved else "Requires changes",
        "summary": result.get("summary", ""),
        "health": format_review_health(result.get("review_health")),
        "bug_rows": [format_bug_row(bug) for bug in bug_items],
        "security_rows": [format_bug_row(bug) for bug in security_items],
        "impact_warnings": result.get("impact_warnings", []),
    }
