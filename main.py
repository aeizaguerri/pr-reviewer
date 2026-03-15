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


def _cli_graph(args: list[str]) -> None:
    if not args:
        print("Usage:")
        print("  uv run python main.py graph init")
        print("  uv run python main.py graph import <topology.yaml>")
        print("  uv run python main.py graph query <entity-name>")
        sys.exit(1)

    subcmd = args[0]

    if subcmd == "init":
        from src.core.exceptions import GraphError
        from src.knowledge.client import check_health, get_driver
        from src.knowledge.schema import init_schema

        try:
            driver = get_driver()
        except GraphError as exc:
            print(f"Error: could not connect to Neo4j — {exc}")
            sys.exit(1)

        if not check_health():
            print("Error: Neo4j is not reachable. Is it running?")
            sys.exit(1)

        init_schema(driver)
        print("Graph schema initialized (constraints + indexes created).")

    elif subcmd == "import":
        if len(args) < 2:
            print("Usage: uv run python main.py graph import <topology.yaml>")
            sys.exit(1)

        yaml_file = args[1]

        from src.core.exceptions import GraphError
        from src.knowledge.client import get_driver
        from src.knowledge.population import load_topology, populate_graph

        try:
            topology = load_topology(yaml_file)
        except FileNotFoundError as exc:
            print(f"Error: {exc}")
            sys.exit(1)
        except Exception as exc:
            # Covers yaml.YAMLError and pydantic.ValidationError
            print(f"Error: invalid topology file — {exc}")
            sys.exit(1)

        try:
            driver = get_driver()
        except GraphError as exc:
            print(f"Error: could not connect to Neo4j — {exc}")
            sys.exit(1)

        try:
            stats = populate_graph(driver, topology)
        except Exception as exc:
            print(f"Error: graph import failed — {exc}")
            sys.exit(1)

        print(
            f"Graph populated: {stats['nodes_created']} nodes, "
            f"{stats['relationships_created']} relationships."
        )

    elif subcmd == "query":
        if len(args) < 2:
            print("Usage: uv run python main.py graph query <entity-name> [--consumers] [--by-path]")
            sys.exit(1)

        entity_name = args[1]
        flag_consumers = "--consumers" in args
        flag_by_path = "--by-path" in args

        from src.core.exceptions import GraphError
        from src.knowledge.client import get_driver
        from src.knowledge.queries import (
            find_consumers,
            find_impact_by_path,
            search_entities,
        )

        try:
            driver = get_driver()
        except GraphError as exc:
            print(f"Error: could not connect to Neo4j — {exc}")
            sys.exit(1)

        try:
            if flag_by_path:
                results = find_impact_by_path(driver, entity_name)
                if results:
                    print(f"Impact analysis for path '{entity_name}':")
                    for r in results:
                        print(f"  Entity: {r['entity_name']} ({r['entity_type']})")
                        print(f"    Consumers: {', '.join(r['consumers'])}")
                else:
                    print(f"No graph entities match path '{entity_name}'.")

            elif flag_consumers:
                results = find_consumers(driver, entity_name)
                if results:
                    print(f"Consumers of '{entity_name}':")
                    for r in results:
                        print(f"  - {r['service']} (repo: {r['repository']})")
                else:
                    print(f"No consumers found for '{entity_name}'.")

            else:
                results = search_entities(driver, entity_name)
                if results:
                    print(f"Entities matching '{entity_name}':")
                    for r in results:
                        print(f"  [{r['label']}] {r['name']}", end="")
                        if r.get("description"):
                            print(f" — {r['description']}", end="")
                        print()
                else:
                    print(f"Entity '{entity_name}' not found in the knowledge graph.")
        except Exception as exc:
            print(f"Error: query failed — {exc}")
            sys.exit(1)

    else:
        print(f"Unknown graph subcommand '{subcmd}'. Use: init, import, query.")
        sys.exit(1)


def main() -> None:
    args = sys.argv[1:]

    if not args:
        print("Usage:")
        print("  uv run python main.py review <owner/repo> <pr_number> [--debug]")
        print("  uv run python main.py serve")
        print("  uv run python main.py graph <init|import|query>")
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

    elif command == "graph":
        _cli_graph(args[1:])

    else:
        print(f"Unknown command '{command}'. Use 'review', 'serve', or 'graph'.")
        sys.exit(1)


if __name__ == "__main__":
    main()
