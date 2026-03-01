import logging
import sys

import uvicorn
from fastapi import FastAPI, HTTPException, Request

from src.reviewer.agent import review_pr, review_pr_debug


# ---------------------------------------------------------------------------
# FastAPI webhook app
# ---------------------------------------------------------------------------

app = FastAPI(title="PR Code Reviewer")


@app.post("/webhook/github")
async def github_webhook(request: Request):
    """Receives GitHub PR webhook events and triggers the code review."""
    payload = await request.json()

    action = payload.get("action", "")
    if action not in ("opened", "synchronize"):
        return {"status": "skipped", "reason": f"action '{action}' not handled"}

    pr = payload.get("pull_request", {})
    pr_number = pr.get("number")
    repo_full = payload.get("repository", {}).get("full_name", "")

    if not pr_number or "/" not in repo_full:
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    owner, repo = repo_full.split("/", 1)

    result = review_pr(owner=owner, repo=repo, pr_number=pr_number)
    return {
        "status": "reviewed",
        "approved": result.approved,
        "bugs_found": len(result.bugs),
        "summary": result.summary,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli_review(repo_slug: str, pr_number: int, debug: bool = False) -> None:
    if "/" not in repo_slug:
        print(f"Error: repo must be in 'owner/repo' format, got '{repo_slug}'")
        sys.exit(1)

    owner, repo = repo_slug.split("/", 1)

    if debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        print(f"\n[DEBUG] Reviewing PR #{pr_number} in {owner}/{repo}\n{'='*60}")
        review_pr_debug(owner=owner, repo=repo, pr_number=pr_number)
        return

    print(f"Reviewing PR #{pr_number} in {owner}/{repo} ...")
    result = review_pr(owner=owner, repo=repo, pr_number=pr_number)

    print(f"\n{'='*60}")
    print(f"Summary : {result.summary}")
    print(f"Approved: {result.approved}")
    print(f"Bugs    : {len(result.bugs)}")
    for bug in result.bugs:
        print(f"\n  [{bug.severity.upper()}] {bug.file}:{bug.line}")
        print(f"  {bug.description}")
        print(f"  Fix: {bug.suggestion}")
    print(f"{'='*60}\n")


def _cli_serve() -> None:
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)


def main() -> None:
    args = sys.argv[1:]

    if not args:
        print("Usage:")
        print("  uv run python main.py review <owner/repo> <pr_number> [--debug]")
        print("  uv run python main.py serve")
        sys.exit(0)

    command = args[0]

    if command == "review":
        positional = [a for a in args[1:] if not a.startswith("--")]
        debug = "--debug" in args
        if len(positional) != 2:
            print("Usage: uv run python main.py review <owner/repo> <pr_number> [--debug]")
            sys.exit(1)
        _cli_review(repo_slug=positional[0], pr_number=int(positional[1]), debug=debug)

    elif command == "serve":
        _cli_serve()

    else:
        print(f"Unknown command '{command}'. Use 'review' or 'serve'.")
        sys.exit(1)


if __name__ == "__main__":
    main()
