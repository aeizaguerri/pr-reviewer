import json
import logging

from agno.agent import Agent
from agno.models.openai.like import OpenAILike

from src.core.config import Config
from src.reviewer.models import BugReport, ReviewOutput
from src.reviewer.prompts import REVIEWER_INSTRUCTIONS, _build_impact_section
from src.reviewer.tools import fetch_pr_data, post_review_comments

logger = logging.getLogger(__name__)


def _build_agent(debug: bool = False) -> Agent:
    model_id, base_url, api_key = Config.get_model_config()

    return Agent(
        id="pr-code-reviewer",
        model=OpenAILike(
            id=model_id,
            base_url=base_url,
            api_key=api_key,
        ),
        instructions=REVIEWER_INSTRUCTIONS,
        output_schema=ReviewOutput,
        markdown=False,
        debug_mode=debug,
    )


def _make_prompt(pr_title: str, diff_text: str) -> str:
    return (
        f"PR title: {pr_title}\n\n"
        "Below is the unified diff for this pull request. "
        "Analyse it for bugs and produce a ReviewOutput.\n\n"
        f"{diff_text}"
    )


def _bugs_to_comments(bugs: list[BugReport]) -> list[dict]:
    return [
        {"path": bug.file, "line": bug.line, "body": f"**[{bug.severity.upper()}]** {bug.description}\n\n**Suggestion:** {bug.suggestion}"}
        for bug in bugs
    ]


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
                logger.warning(
                    "Graph enrichment skipped: Neo4j is not reachable."
                )
        except Exception as exc:
            logger.warning(
                "Graph enrichment failed — continuing without it: %s", exc
            )
            impact_result = None

    # Step 3: run LLM analysis with structured output
    agent = _build_agent(debug=False)
    run = agent.run(prompt)
    result: ReviewOutput = run.content

    # Step 4: attach impact warnings to result
    if impact_result is not None:
        result.impact_warnings = impact_result.warnings

    # Step 5: post inline comments via GitHub API
    if result.bugs:
        comments = json.dumps(_bugs_to_comments(result.bugs))
        post_review_comments(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            commit_sha=head_sha,
            comments=comments,
            summary=result.summary,
        )

    return result


def review_pr_debug(owner: str, repo: str, pr_number: int) -> None:
    """Run the reviewer with full verbose output streamed to the terminal."""
    # Step 1: fetch diff programmatically
    print("=== [fetch_pr_data] fetching diff from GitHub ===")
    diff_text, head_sha, pr_title = fetch_pr_data(owner, repo, pr_number)
    print(f"PR title: {pr_title}")
    print(f"head_sha: {head_sha}")
    print(f"--- diff ({len(diff_text)} chars) ---\n{diff_text[:2000]}{'...' if len(diff_text) > 2000 else ''}")

    # Step 2: graph enrichment debug
    prompt = _make_prompt(pr_title, diff_text)
    impact_result = None

    if Config.ENABLE_GRAPH_ENRICHMENT:
        print("\n=== [graph enrichment] ENABLE_GRAPH_ENRICHMENT=true ===")
        try:
            from src.knowledge.client import check_health, get_driver
            from src.knowledge.queries import find_consumers_of_paths

            changed_paths = _extract_changed_paths(diff_text)
            print(f"Files scanned: {len(changed_paths)}")
            for p in changed_paths:
                print(f"  - {p}")

            if check_health():
                driver = get_driver()
                impact_result = find_consumers_of_paths(
                    driver,
                    changed_paths,
                    timeout=Config.GRAPH_QUERY_TIMEOUT,
                )
                print(f"Impact warnings found: {len(impact_result.warnings)}")
                print(f"Query time: {impact_result.query_time_ms:.1f}ms")

                if impact_result.warnings:
                    impact_section = _build_impact_section(impact_result)
                    if impact_section:
                        prompt = impact_section + "\n\n" + prompt
                        print("\n--- Injected impact section ---")
                        print(impact_section)
                        print("--- End of impact section ---")
            else:
                print("Neo4j is not reachable — skipping graph enrichment.")

        except Exception as exc:
            print(f"Graph enrichment error (continuing without it): {exc}")
            impact_result = None
    else:
        print("\n[graph enrichment] ENABLE_GRAPH_ENRICHMENT=false — skipped.")

    print("\n=== [agent.run] sending diff to LLM ===")

    # Step 3: run LLM analysis (streamed)
    agent = _build_agent(debug=True)
    run = agent.run(prompt)
    result: ReviewOutput = run.content

    # Step 4: attach impact warnings
    if impact_result is not None:
        result.impact_warnings = impact_result.warnings

    print("\n=== [ReviewOutput] ===")
    print(result.model_dump_json(indent=2))

    # Step 5: post inline comments
    if result.bugs:
        print("\n=== [post_review_comments] posting to GitHub ===")
        comments = json.dumps(_bugs_to_comments(result.bugs))
        outcome = post_review_comments(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            commit_sha=head_sha,
            comments=comments,
            summary=result.summary,
        )
        print(outcome)
    else:
        print("\nNo bugs found — skipping post_review_comments.")
