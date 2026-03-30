"""Backend entrypoint — FastAPI application with webhook and CLI support."""

import hashlib
import hmac
import logging
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.api.v1.routes import router
from backend.core.config import BackendConfig
from src.core.config import Config
from src.core.logging_config import configure_logging
from src.reviewer.agent import review_pr, review_pr_debug

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Webhook signature validation
# ---------------------------------------------------------------------------

WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")


async def _verify_github_signature(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
) -> None:
    """Validate GitHub webhook HMAC-SHA256 signature.

    If GITHUB_WEBHOOK_SECRET is not set, the endpoint is disabled (501).
    If signature is missing or invalid, returns 401.
    """
    if not WEBHOOK_SECRET:
        raise HTTPException(
            status_code=501,
            detail="Webhook is disabled: GITHUB_WEBHOOK_SECRET is not configured.",
        )

    body = await request.body()
    mac = hmac.new(WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256)
    expected_sig = "sha256=" + mac.hexdigest()

    if not hmac.compare_digest(expected_sig, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler — configures logging on startup.

    This ensures that direct ``uvicorn backend.main:app`` invocations (which
    bypass ``main()``) still have logging configured before any request lands.
    """
    configure_logging()
    logger.info("PR Reviewer backend started")
    yield


app = FastAPI(title="PR Code Reviewer API", lifespan=lifespan)

# CORS middleware
_cors_origins = [o.strip() for o in BackendConfig.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(router)


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------


@app.post("/api/v1/webhook/github", status_code=202)
async def github_webhook(
    request: Request,
    _: None = Depends(_verify_github_signature),
):
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

    # L1: Author association gating — skip untrusted authors
    author_association = (pr.get("author_association") or "NONE").upper()
    _trusted_raw = {
        a.strip().upper() for a in Config.TRUSTED_AUTHOR_ASSOCIATIONS.split(",")
    }
    trusted = {a for a in _trusted_raw if a}
    if not trusted:
        logger.warning(
            "TRUSTED_AUTHOR_ASSOCIATIONS resolved to empty set — "
            "falling back to default: OWNER,MEMBER,COLLABORATOR"
        )
        trusted = {"OWNER", "MEMBER", "COLLABORATOR"}
    if author_association not in trusted:
        return {
            "status": "skipped",
            "reason": f"untrusted author association: {author_association}",
        }

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
        configure_logging("DEBUG")
        print(f"\n[DEBUG] Reviewing PR #{pr_number} in {owner}/{repo}\n{'=' * 60}")
        review_pr_debug(owner=owner, repo=repo, pr_number=pr_number)
        return

    print(f"Reviewing PR #{pr_number} in {owner}/{repo} ...")
    result = review_pr(owner=owner, repo=repo, pr_number=pr_number)

    print(f"\n{'=' * 60}")
    print(f"Summary : {result.summary}")
    print(f"Approved: {result.approved}")
    print(f"Bugs    : {len(result.bugs)}")
    for bug in result.bugs:
        print(f"\n  [{bug.severity.upper()}] {bug.file}:{bug.line}")
        print(f"  {bug.description}")
        print(f"  Fix: {bug.suggestion}")
    print(f"{'=' * 60}\n")


def _cli_serve() -> None:
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)


def _cli_graph(args: list[str]) -> None:
    if not args:
        print("Usage:")
        print("  uv run python -m backend.main graph init")
        print("  uv run python -m backend.main graph import <topology.yaml>")
        print("  uv run python -m backend.main graph query <entity-name>")
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
            print("Usage: uv run python -m backend.main graph import <topology.yaml>")
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
            print(
                "Usage: uv run python -m backend.main graph query <entity-name> [--consumers] [--by-path]"
            )
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
    configure_logging()
    args = sys.argv[1:]

    if not args:
        print("Usage:")
        print(
            "  uv run python -m backend.main review <owner/repo> <pr_number> [--debug]"
        )
        print("  uv run python -m backend.main serve")
        print("  uv run python -m backend.main graph <init|import|query>")
        sys.exit(0)

    command = args[0]

    if command == "review":
        positional = [a for a in args[1:] if not a.startswith("--")]
        debug = "--debug" in args
        if len(positional) != 2:
            print(
                "Usage: uv run python -m backend.main review <owner/repo> <pr_number> [--debug]"
            )
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
