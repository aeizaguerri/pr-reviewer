---
name: pr-reviewer-testing
description: "Trigger: tests, pytest, test structure, fixtures. Create and run pr-reviewer tests in the package-owned layout."
license: Apache-2.0
metadata:
  author: aeizaguerri
  version: "1.0"
---

# pr-reviewer Testing

## Activation Contract

Use this skill when adding, moving, debugging, or running tests in this repo.

## Hard Rules

- Do not recreate root `tests/`; tests live with the package they verify.
- Keep fixtures local to the nearest package `conftest.py`; avoid shared global fixtures.
- Do not build. Do not install dependencies unless the user explicitly asks.
- Do not touch `uv.lock` for pure test movement or fixture-only changes.
- Preserve behavior when relocating tests; production code changes require a separate reason.

## Decision Gates

| Test target | Location | Command |
|---|---|---|
| Backend/FastAPI | `backend/tests/` | `uv run --no-sync pytest backend/tests/` |
| Reviewer domain | `src/reviewer/tests/` | `uv run --no-sync pytest src/reviewer/tests/` |
| Knowledge graph | `src/knowledge/tests/` | `uv run --no-sync pytest src/knowledge/tests/` |
| Core config/logging/observability | `src/core/tests/` | `uv run --no-sync pytest src/core/tests/` |
| Whole repo | configured `testpaths` | `uv run --no-sync pytest` |

## Execution Steps

1. Put new tests beside the package under test: `backend/tests`, `src/reviewer/tests`, `src/knowledge/tests`, or `src/core/tests`.
2. Add fixtures to that package's `conftest.py` only when multiple tests in that package use them.
3. Prefer explicit mocks for external systems: GitHub, LLM/Agno, Neo4j, Opik, and FastAPI lifespan side effects.
4. Run focused collection first: `uv run --no-sync pytest <path> --collect-only`.
5. Run the focused suite, then root `uv run --no-sync pytest` when changing discovery, fixtures, or shared config.
6. For Neo4j-dependent tests, use mocks by default; mark true external integration tests with `@pytest.mark.integration`.

## Output Contract

Return the test files changed, fixtures added or moved, commands run, pass/fail counts, and any warnings that are unrelated but visible during pytest startup.

## References

- `pyproject.toml` — root pytest discovery for all package-owned suites.
- `backend/pyproject.toml` — backend-local pytest discovery.
