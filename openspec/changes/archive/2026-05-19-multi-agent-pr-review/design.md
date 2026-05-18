# Design: multi-agent-pr-review

## Overview

Replace the current mono-agent path in `src/reviewer/agent.py` with a primary multi-agent orchestrator. No runtime feature flag and no legacy mono-agent fallback will be designed. Existing public contracts remain: `review_pr()` / `review_pr_with_config()` return `ReviewOutput`; `backend/services/reviewer.py::run_review()` returns `ReviewResponse`.

## Architecture

Add `src/reviewer/orchestrator.py` as the deterministic coordinator:

1. Fetch PR data once via `fetch_pr_data(owner, repo, pr_number, github_token=...)`.
2. Extract changed paths once with existing `_extract_changed_paths(diff_text)`.
3. Enrich graph once with existing `_enrich_with_graph(diff_text)` and `_build_impact_section()`.
4. Build one immutable shared context string from `impact_section + _make_prompt(pr_title, diff_text)` plus changed-path metadata.
5. Fan out concurrently:
   - Bug Reviewer A/B through an Agno `Team` configured for blind broadcast / no member-to-member context sharing.
   - Security Reviewer as a read-only specialist agent.
   - Cross-Repo Impact Reviewer as a read-only specialist agent.
6. Normalize each specialist result into internal Pydantic models.
7. Run deterministic normalizer/pre-deduper, then judge/deduper/synthesizer.
8. Post to GitHub exactly once, after valid `ReviewOutput` synthesis, using existing `post_review_comments()` only.

`review_pr_with_config()` becomes a thin delegate to `run_multi_agent_review(...)`. `review_pr()` uses `Config.get_model_config()` and provider structured-output support, then delegates to the same orchestrator.

## Data Contracts

Keep `src/reviewer/models.py::BugReport` and `ReviewOutput` unchanged. Add internal-only models in `src/reviewer/models.py` or `src/reviewer/orchestrator.py`:

- `SpecialistBugOutput(bugs: list[BugReport])`
- `SpecialistImpactOutput(impact_warnings: list[ImpactWarning])`
- `SpecialistFailure(role: str, reason: str)`
- `ReviewContext(owner, repo, pr_number, head_sha, pr_title, diff_text, changed_paths, impact_result, prompt)`

Security findings use `BugReport`. Cross-repo findings use existing `ImpactWarning` and must be grounded against graph warnings and changed paths.

## Agents and Prompts

In `src/reviewer/prompts.py`, add role-specific instructions:

- `BUG_REVIEWER_INSTRUCTIONS`: code defects only; exclude security and cross-repo impact.
- `SECURITY_REVIEWER_INSTRUCTIONS`: CWE-style vulnerabilities only; exclude general bugs and impact analysis.
- `CROSS_REPO_IMPACT_REVIEWER_INSTRUCTIONS`: may only cite changed paths and graph `ImpactWarning` evidence; empty output when no evidence exists.
- `JUDGE_INSTRUCTIONS` / `SYNTHESIZER_INSTRUCTIONS`: dedupe, merge, and produce `ReviewOutput`-compatible data.

Specialist agents are built with `OpenAILike` and no tools. No specialist or Team receives `github_token` or `post_review_comments`.

## Normalization and Synthesis

Create deterministic helpers before any LLM judge decision:

- Parse structured `run.content` when provider supports `output_schema`.
- Fallback to `json.loads(raw)` + Pydantic validation when structured output is unavailable or malformed.
- Log parse failures with `_log_full_llm_response(raw, owner, repo, pr_number, specialist=...)` or an equivalent specialist-aware extension.
- Pre-dedupe by normalized key `(file, line, category inferred from role/description)` for bugs and `(changed_file, affected_service)` for impact warnings.

The judge receives only Bug Reviewer A/B outputs. The synthesizer merges judged bugs + security bugs, escalates severity on overlap, attaches grounded impact warnings plus graph-derived warnings, computes `approved=False` for critical bugs/security or high impact warnings, and returns `ReviewOutput`.

## Failure and Timeout Policy

Each specialist runs under configurable timeout constants in `src/reviewer/orchestrator.py` or `src/core/config.py` (e.g. `REVIEW_SPECIALIST_TIMEOUT_SECONDS`, default 120). Use `asyncio.gather(..., return_exceptions=True)` / `asyncio.wait_for()` so one failure does not cancel others.

- Individual specialist failure: log, contribute empty output/failure marker, continue.
- Both bug reviewers fail: final bugs may come from Security only; otherwise empty with degraded summary.
- Cross-Repo failure: preserve graph-derived warnings.
- Judge/synthesizer failure: return `_parse_failure_result(impact_result)`; do not post.
- Fetch failure: preserve current public behavior consistently with existing `review_pr_with_config()` expectations.

## Exactly-Once Posting

Keep posting in `src/reviewer/tools.py`. The orchestrator is the only caller. If `ReviewOutput.bugs` is non-empty and existing posting mode allows it, call `post_review_comments(...)` once with `_bugs_to_comments(result.bugs)`, synthesized `summary`, original `head_sha`, and `github_token`. Empty bug list means no posting.

## File Changes

- `src/reviewer/orchestrator.py`: new orchestrator, fan-out, parsing, grounding, synthesis, posting boundary.
- `src/reviewer/agent.py`: delegate public entrypoints; retain reusable helpers or move them to orchestrator utilities.
- `src/reviewer/models.py`: internal specialist output models if not kept private.
- `src/reviewer/prompts.py`: role prompts.
- `backend/services/reviewer.py`: no response-shape change; tests may mock new delegate path.
- `backend/core/config.py` / `src/core/config.py`: timeout config only; no multi-agent enable flag.
- Tests under `src/reviewer/tests` and `backend/tests` updated from mono-agent internals to multi-agent behavior.

## Test Plan (strict TDD)

Runner: `uv run pytest`. Follow RED, GREEN, TRIANGULATE, REFACTOR.

Add tests for: `review_pr_with_config()` delegates to orchestrator and has no mono-agent branch; single fetch/enrich; Bug A/B identical prompts and no contamination; Security/Cross-Repo scheduled in parallel; structured-output and JSON fallback per specialist; deterministic dedupe; impact grounding; specialist timeout/failure isolation; judge/synthesizer fatal fallback; exactly-once posting after synthesis; no specialist posting tools; backend `ReviewResponse` compatibility. Update/remove tests asserting `_build_agent` or single `_run_llm` from public entrypoints.

## Rollout

Implement in small TDD slices: routing seam, context builder, specialist runners, Bug Team, parallel fan-out, normalizer/deduper, synthesizer, posting invariant, backend regression. Rollback is git revert of this iteration; no runtime fallback path is maintained.
