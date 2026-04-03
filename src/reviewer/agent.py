import html
import json
import logging
import re

from agno.agent import Agent
from agno.models.openai.like import OpenAILike

from src.core.config import Config
from src.core.observability import track_if_enabled
from src.reviewer.models import BugReport, ReviewOutput
from src.reviewer.prompts import REVIEWER_INSTRUCTIONS, _build_impact_section
from src.reviewer.tools import fetch_pr_data, post_review_comments

logger = logging.getLogger(__name__)


def _build_agent(debug: bool = False) -> Agent:
    model_id, base_url, api_key = Config.get_model_config()

    # Use structured output only for providers that support it
    use_structured = Config.DEFAULT_PROVIDER in ("openai",)

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
    return (
        "Below is the pull request to review. Analyse the diff for bugs and produce a ReviewOutput.\n\n"
        f"<pr_title>{clean_title}</pr_title>\n\n"
        "<diff_content>\n"
        f"{safe_diff}\n"
        "</diff_content>"
    )


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
    return run.content if isinstance(run.content, str) else json.dumps(run.content.model_dump() if hasattr(run.content, "model_dump") else run.content)


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


@track_if_enabled()
def review_pr(owner: str, repo: str, pr_number: int) -> ReviewOutput:
    """Run the reviewer on the given pull request (silent mode)."""
    # Step 1: fetch diff programmatically
    diff_text, head_sha, pr_title = fetch_pr_data(owner, repo, pr_number)

    # Step 2: graph enrichment (optional, behind feature toggle)
    prompt = _make_prompt(pr_title, diff_text)
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
                            prompt = impact_section + "\n\n" + prompt
            else:
                logger.warning("Graph enrichment skipped: Neo4j is not reachable.")
        except Exception as exc:
            logger.warning("Graph enrichment failed — continuing without it: %s", exc)
            impact_result = None

    # Step 3: run LLM analysis with structured output
    agent = _build_agent(debug=False)
    raw = _run_llm(agent, prompt)

    try:
        data = json.loads(raw)
        result = ReviewOutput(**data)
    except Exception:
        logger.warning("Agent returned unparseable output: %s", raw[:200])
        result = ReviewOutput(
            summary=f"Error: Agent failed to produce valid output. Raw response: {raw[:500]}",
            bugs=[],
            approved=False,
        )

    # Step 4: attach impact warnings to result
    if impact_result is not None:
        result.impact_warnings = impact_result.warnings

    # Step 5: post inline comments via GitHub API
    if result.bugs:
        comments = json.dumps(_bugs_to_comments(result.bugs))
        gh_result = post_review_comments(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            commit_sha=head_sha,
            comments=comments,
            summary=result.summary,
        )
        logger.info("GitHub review post result: %s", gh_result)

    return result


@track_if_enabled(capture_input=False)
def review_pr_with_config(
    owner: str,
    repo: str,
    pr_number: int,
    provider_config: tuple[str, str, str],
    github_token: str = "",
    supports_structured_output: bool = True,
) -> ReviewOutput:
    """Run the reviewer with explicit provider config (no env var reads).

    Use this from the Streamlit UI or any caller that provides credentials
    directly. The existing review_pr() remains unchanged for CLI/webhook use.

    Args:
        owner: Repository owner (user or org).
        repo: Repository name.
        pr_number: Pull request number.
        provider_config: Tuple of (model_id, base_url, api_key) — matches the
            shape returned by build_provider_config() and Config.get_model_config().
        github_token: GitHub personal access token. When omitted, falls back to
            the GITHUB_ACCESS_TOKEN environment variable.
        supports_structured_output: Whether the provider supports structured outputs.

    Returns:
        ReviewOutput with bugs, summary, and approval status.
    """
    # Step 1: fetch diff
    diff_text, head_sha, pr_title = fetch_pr_data(
        owner, repo, pr_number, github_token=github_token
    )

    # Step 2: graph enrichment (optional, behind feature toggle — same as review_pr)
    prompt = _make_prompt(pr_title, diff_text)
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
                            prompt = impact_section + "\n\n" + prompt
            else:
                logger.warning("Graph enrichment skipped: Neo4j is not reachable.")
        except Exception as exc:
            logger.warning("Graph enrichment failed — continuing without it: %s", exc)
            impact_result = None

    # Step 3: run LLM analysis with injected config
    agent = _build_agent_with_config(
        provider_config,
        supports_structured_output=supports_structured_output,
        debug=False,
    )
    raw = _run_llm(agent, prompt)

    try:
        data = json.loads(raw)
        result = ReviewOutput(**data)
    except Exception:
        logger.warning("Agent returned unparseable output: %s", raw[:200])
        result = ReviewOutput(
            summary=f"Error: Agent failed to produce valid output. Raw response: {raw[:500]}",
            bugs=[],
            approved=False,
        )

    # Step 4: attach impact warnings
    if impact_result is not None:
        result.impact_warnings = impact_result.warnings

    # Step 5: post inline comments via GitHub API
    if result.bugs:
        comments = json.dumps(_bugs_to_comments(result.bugs))
        gh_result = post_review_comments(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            commit_sha=head_sha,
            comments=comments,
            summary=result.summary,
            github_token=github_token,
        )
        logger.info("GitHub review post result: %s", gh_result)

    return result
