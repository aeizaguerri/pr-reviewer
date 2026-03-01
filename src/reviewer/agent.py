import json

from agno.agent import Agent
from agno.models.openai.like import OpenAILike

from src.core.config import Config
from src.reviewer.models import BugReport, ReviewOutput
from src.reviewer.prompts import REVIEWER_INSTRUCTIONS
from src.reviewer.tools import fetch_pr_data, post_review_comments


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


def review_pr(owner: str, repo: str, pr_number: int) -> ReviewOutput:
    """Run the reviewer on the given pull request (silent mode)."""
    # Step 1: fetch diff programmatically
    diff_text, head_sha, pr_title = fetch_pr_data(owner, repo, pr_number)

    # Step 2: run LLM analysis with structured output
    agent = _build_agent(debug=False)
    run = agent.run(_make_prompt(pr_title, diff_text))
    result: ReviewOutput = run.content

    # Step 3: post inline comments via GitHub API
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
    print("=== [agent.run] sending diff to LLM ===")

    # Step 2: run LLM analysis (streamed)
    agent = _build_agent(debug=True)
    run = agent.run(_make_prompt(pr_title, diff_text))
    result: ReviewOutput = run.content

    print("\n=== [ReviewOutput] ===")
    print(result.model_dump_json(indent=2))

    # Step 3: post inline comments
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
