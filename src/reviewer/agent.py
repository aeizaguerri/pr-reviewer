import html
import json
import logging
import os
import re
from pathlib import Path

from agno.agent import Agent
from agno.models.openai.like import OpenAILike

from src.core.config import Config
from src.core.observability import render_prompt, track_if_enabled
from src.reviewer.models import BugReport, ReviewOutput
from src.reviewer.prompts import REVIEWER_INSTRUCTIONS, _build_impact_section

logger = logging.getLogger(__name__)


def _debug_raw_llm_logging_enabled() -> bool:
    return os.getenv("PR_REVIEWER_LOG_RAW_LLM_FAILURES", "false").lower() == "true"


def _log_full_llm_response(raw: str, owner: str, repo: str, pr_number: int) -> None:
    """Log full raw LLM response to a file for debugging."""
    if not _debug_raw_llm_logging_enabled():
        preview = " ".join(raw.split())[:200]
        logger.warning(
            "Agent returned unparseable output for %s/%s#%d. Response length=%d preview=%r",
            owner,
            repo,
            pr_number,
            len(raw),
            preview,
        )
        return

    log_dir = Path("/tmp/pr-reviewer-logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"llm-fail-{owner}-{repo}-{pr_number}.txt"
    log_file.write_text(raw)
    logger.warning("Agent returned unparseable output. Full response logged to %s", log_file)


def _parse_failure_result(impact_result) -> ReviewOutput:
    warnings = impact_result.warnings if impact_result is not None else []
    return ReviewOutput(
        summary="Error: Agent failed to produce valid output.",
        bugs=[],
        approved=False,
        impact_warnings=warnings,
    )


def _build_agent(debug: bool = False) -> Agent:
    model_id, base_url, api_key = Config.get_model_config()

    # Use structured output only for providers that support it
    use_structured = Config.provider_supports_structured_output(Config.DEFAULT_PROVIDER)

    return Agent(
        id="pr-code-reviewer",
        model=OpenAILike(
            id=model_id,
            base_url=base_url,
            api_key=api_key,
        ),
        instructions=REVIEWER_INSTRUCTIONS,
        output_schema=ReviewOutput if use_structured else None,
        markdown=False,
        debug_mode=debug,
    )


def _build_agent_with_config(
    provider_config: tuple[str, str, str],
    supports_structured_output: bool = True,
    debug: bool = False,
) -> Agent:
    """Build an Agent with explicit (model_id, base_url, api_key) — no env reads."""
    model_id, base_url, api_key = provider_config

    # Use structured output only for providers that support it
    use_structured = supports_structured_output

    return Agent(
        id="pr-code-reviewer",
        model=OpenAILike(
            id=model_id,
            base_url=base_url,
            api_key=api_key,
        ),
        instructions=REVIEWER_INSTRUCTIONS,
        output_schema=ReviewOutput if use_structured else None,
        markdown=False,
        debug_mode=debug,
    )


def _sanitize_title(title: str) -> str:
    """Strip control characters and collapse whitespace from PR title."""
    # Remove all control characters (C0 + C1) except space, plus Unicode BIDI/invisible chars
    cleaned = re.sub(
        r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202e\u2066-\u2069\ufeff]",
        " ",
        title,
    )
    # Collapse multiple spaces
    return " ".join(cleaned.split())


def _make_prompt(pr_title: str, diff_text: str) -> str:
    clean_title = html.escape(_sanitize_title(pr_title))
    safe_diff = html.escape(diff_text)
    return render_prompt("pr_review_prompt", pr_title=clean_title, diff_text=safe_diff)


def _bugs_to_comments(bugs: list[BugReport]) -> list[dict]:
    return [
        {
            "path": bug.file,
            "line": bug.line,
            "body": f"**[{bug.severity.upper()}]** {bug.description}\n\n**Suggestion:** {bug.suggestion}",
        }
        for bug in bugs
    ]


@track_if_enabled(name="llm_call")
def _run_llm(agent: Agent, prompt: str) -> str:
    """Run the agent and return the raw response content as a string."""
    run = agent.run(prompt)
    return (
        run.content
        if isinstance(run.content, str)
        else json.dumps(
            run.content.model_dump() if hasattr(run.content, "model_dump") else run.content
        )
    )


def _extract_changed_paths(diff_text: str) -> list[str]:
    """Extracts unique file paths from the diff text produced by ``fetch_pr_data()``.

    ``fetch_pr_data()`` formats the diff as::

        ### path/to/file.py
        @@ -1,5 +1,6 @@
        ...

    This function parses those ``### <filename>`` header lines and returns a
    deduplicated list of paths in the order they first appear.

    Args:
        diff_text: The diff string returned by ``fetch_pr_data()``.

    Returns:
        Deduplicated list of changed file paths (repo-relative).
    """
    seen: set[str] = set()
    paths: list[str] = []

    for line in diff_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            path = stripped[4:].strip()
            if path and path not in seen:
                seen.add(path)
                paths.append(path)

    return paths


def _enrich_with_graph(
    diff_text: str,
) -> tuple[str, list | None]:
    """Enrich prompt with graph data if available. Returns (prompt, impact_result)."""
    prompt = ""
    impact_result = None

    if Config.ENABLE_GRAPH_ENRICHMENT:
        try:
            from src.knowledge.client import check_health, get_driver
            from src.knowledge.queries import find_consumers_of_paths

            if check_health():
                changed_paths = _extract_changed_paths(diff_text)
                if changed_paths:
                    driver = get_driver()
                    impact_result = find_consumers_of_paths(
                        driver,
                        changed_paths,
                        timeout=Config.GRAPH_QUERY_TIMEOUT,
                    )
                    if impact_result.warnings:
                        impact_section = _build_impact_section(impact_result)
                        if impact_section:
                            prompt = impact_section + "\n\n"
            else:
                logger.warning("Graph enrichment skipped: Neo4j is not reachable.")
        except Exception as exc:
            logger.warning("Graph enrichment failed — continuing without it: %s", exc)
            impact_result = None

    return prompt, impact_result


@track_if_enabled()
def review_pr(owner: str, repo: str, pr_number: int) -> ReviewOutput:
    """Run the reviewer on the given pull request (silent mode).

    Delegates to the multi-agent orchestrator. The mono-agent inline path has
    been superseded.
    """
    # Local import avoids circular dependency.
    from src.reviewer.orchestrator import run_multi_agent_review

    provider_config = Config.get_model_config()
    supports_structured = Config.provider_supports_structured_output(Config.DEFAULT_PROVIDER)

    # Backward-compatible single-config fan-out
    role_configs = {
        "bug": provider_config,
        "security": provider_config,
        "cross_repo": provider_config,
    }

    return run_multi_agent_review(
        owner=owner,
        repo=repo,
        pr_number=pr_number,
        role_configs=role_configs,
        supports_structured_output=supports_structured,
    )


@track_if_enabled(capture_input=False)
def review_pr_with_config(
    owner: str,
    repo: str,
    pr_number: int,
    provider_config: tuple[str, str, str],
    github_token: str = "",
    supports_structured_output: bool = True,
    role_configs: dict[str, tuple[str, str, str]] | None = None,
) -> ReviewOutput:
    """Run the reviewer with explicit provider config (no env var reads).

    Delegates to the multi-agent orchestrator. The mono-agent path has been
    superseded by the multi-agent review pipeline.

    Args:
        owner: Repository owner (user or org).
        repo: Repository name.
        pr_number: Pull request number.
        provider_config: Tuple of (model_id, base_url, api_key). Used when
            role_configs is not provided.
        github_token: GitHub personal access token.
        supports_structured_output: Whether the provider supports structured outputs.
        role_configs: Optional per-role config dict. When provided, it overrides
            the uniform provider_config fan-out.

    Returns:
        ReviewOutput with bugs, summary, and approval status.
    """
    # Local import avoids circular dependency: orchestrator imports helpers from agent.
    from src.reviewer.orchestrator import run_multi_agent_review

    if role_configs is None:
        # Backward-compatible single-config fan-out into per-role dict
        role_configs = {
            "bug": provider_config,
            "security": provider_config,
            "cross_repo": provider_config,
        }

    return run_multi_agent_review(
        owner=owner,
        repo=repo,
        pr_number=pr_number,
        role_configs=role_configs,
        github_token=github_token,
        supports_structured_output=supports_structured_output,
    )
