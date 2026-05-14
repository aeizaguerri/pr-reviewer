# Apply Progress: multi-agent-pr-review

Status: PR 1, PR 2, and PR 3 implementation slices are applied in the working tree. The remaining SDD gate is the final integration check (`tasks.md` 3.12), followed by `/sdd-verify`.

## PR 1: Contracts, Context, and Routing Seam

### TDD Cycle Evidence

| Task | RED | GREEN | TRIANGULATE / REFACTOR |
| ---- | --- | ----- | ---------------------- |
| 1.1 Routing tests | Wrote `test_multi_agent_routing.py`; initial failures covered missing orchestrator seam / stub behavior. | Patched correct targets (`src.reviewer.orchestrator.run_multi_agent_review`, `src.reviewer.orchestrator.fetch_pr_data`) after wiring `agent.py`. | Removed redundant patches; routing tests clean. |
| 1.2 Specialist models | N/A (implementation-only task). | Added `SpecialistBugOutput`, `SpecialistSecurityOutput`, `SpecialistImpactOutput`, `SpecialistFailure`, and `ReviewContext` to `src/reviewer/models.py`. | Verified public `BugReport` / `ReviewOutput` contracts stayed unchanged. |
| 1.3 Timeout config | N/A. | Added `REVIEW_SPECIALIST_TIMEOUT_SECONDS` to `src/core/config.py` and `backend/core/config.py`. | — |
| 1.4 Role prompts | N/A. | Added lazy-loaded role prompts for Bug, Security, Cross-Repo Impact, and Judge in `src/reviewer/prompts.py`. | Kept existing lazy-load prompt pattern. |
| 1.5 Context builder tests | Wrote `test_orchestrator_context.py`; initial failures covered missing orchestrator module/helper. | Created `src/reviewer/orchestrator.py` with `build_review_context()`. | Fixed patch targets to orchestrator-local imports. |
| 1.6 `build_review_context()` | N/A. | Implemented changed-path extraction, graph enrichment, shared prompt assembly, and `ReviewContext` return. | Kept reusable helpers in `agent.py` and imported them from orchestrator. |
| 1.7 Stub `run_multi_agent_review()` | N/A. | Added initial orchestrator entrypoint that fetches once, builds context, and stubs fan-out. | Later replaced by async core + sync wrapper in PR 3. |
| 1.8 Public routing | N/A. | `review_pr_with_config()` delegates to `run_multi_agent_review()`. | Preserved helper functions still imported by orchestrator. |
| 1.9 Routing + shape tests | Extended routing tests around orchestrator call, single fetch/context build, and `ReviewOutput` shape. | Tests pass after stub and wiring. | Updated `test_review_pr_with_config.py` for the new seam earlier than originally planned. |
| 1.10 Backend timeout config | N/A. | Mirrored timeout config into `backend/core/config.py`. | — |
| 1.11 PR 1 gate | Ran focused and reviewer-suite checks during PR1. | `uv run pytest src/reviewer/tests/test_multi_agent_routing.py src/reviewer/tests/test_orchestrator_context.py -v` → 6 passed; `uv run pytest src/reviewer/tests/ -v -m "not integration"` → 98 passed; targeted Ruff clean. | Fixed Ruff issues around unused imports / variables. |

### PR 1 Files Changed

| File | Action | Notes |
| ---- | ------ | ----- |
| `src/reviewer/models.py` | Modified | Added internal specialist/context models. |
| `src/reviewer/prompts.py` | Modified | Added role-specific lazy prompt constants. |
| `src/core/config.py` | Modified | Added `REVIEW_SPECIALIST_TIMEOUT_SECONDS`. |
| `backend/core/config.py` | Modified | Added backend config parity. |
| `src/reviewer/orchestrator.py` | Created | Context builder + initial orchestrator seam. |
| `src/reviewer/agent.py` | Modified | `review_pr_with_config()` delegates to orchestrator. |
| `src/reviewer/tests/test_multi_agent_routing.py` | Created | Routing seam tests. |
| `src/reviewer/tests/test_orchestrator_context.py` | Created | Context builder tests. |
| `src/reviewer/tests/test_review_pr_with_config.py` | Modified | Updated for multi-agent routing. |

## PR 2: Specialist Agent Runners and Bug Team

### TDD Cycle Evidence

| Task | RED | GREEN | TRIANGULATE / REFACTOR |
| ---- | --- | ----- | ---------------------- |
| 2.1 Bug Reviewer A/B tests | Added `test_bug_team.py` covering identical prompt delivery, no reviewer cross-contamination, same provider model, and no GitHub/posting tools. | Tests pass against `_run_bug_reviewers()`. | Mocked Team responses through `member_responses` to align with real Agno output shape. |
| 2.2 Bug Reviewer A/B Team | N/A after RED tests. | Implemented `_run_bug_reviewers()` using `Agent`, `OpenAILike`, and `Team(mode="broadcast")` with `share_member_interactions=False` and `show_members_responses=True`. | Added `_iter_team_messages()` and `_maybe_await()` compatibility helpers for mocked and real Agno APIs; parser preserves provider/raw content. |
| 2.3 Security Reviewer tests | Added `test_security_reviewer.py` covering read-only agent construction, security instructions + shared prompt, parse failure, and timeout handling. | Tests pass against `_run_security_reviewer()`. | Security parse failures return `SpecialistFailure(role="security-reviewer")`. |
| 2.4 Security Reviewer runner | N/A after RED tests. | Implemented `_run_security_reviewer()` with `Agent.arun()`, `asyncio.wait_for()`, structured-output schema toggle, parse fallback, timeout/failure isolation. | Uses common `_build_agent()` helper so no tools or GitHub token are injected. |
| 2.5 Cross-Repo Impact tests | Added `test_cross_repo_reviewer.py` covering no-evidence short-circuit, no posting tools/token, parse success/failure, and timeout handling. | Tests pass against `_run_cross_repo_reviewer()`. | No graph warnings short-circuit to empty `SpecialistImpactOutput`, avoiding unsupported impact claims. |
| 2.6 Cross-Repo Impact runner | N/A after RED tests. | Implemented `_run_cross_repo_reviewer()` with graph-evidence gate, read-only specialist agent, structured-output schema toggle, parse fallback, timeout/failure isolation. | Preserves grounding rule by returning empty output when no impact evidence exists. |
| 2.7 PR 2 gate | Specialist runner test files were added for Bug Team, Security, and Cross-Repo Impact. | Implementation satisfies the per-runner test coverage in the working tree. | Full final validation is deferred to 3.12 / `/sdd-verify`. |

### PR 2 Files Changed

| File | Action | Notes |
| ---- | ------ | ----- |
| `src/reviewer/orchestrator.py` | Modified | Added read-only `_build_agent()`, Bug A/B Team, Security runner, Cross-Repo runner, parsing helpers, and async compatibility helpers. |
| `src/reviewer/tests/test_bug_team.py` | Created | Bug Reviewer A/B Team tests. |
| `src/reviewer/tests/test_security_reviewer.py` | Created | Security Reviewer tests. |
| `src/reviewer/tests/test_cross_repo_reviewer.py` | Created | Cross-Repo Impact Reviewer tests. |

## PR 3: Fan-Out, Judge/Deduper/Synthesizer, Exactly-Once Posting, and Cleanup

### TDD Cycle Evidence

| Task | RED | GREEN | TRIANGULATE / REFACTOR |
| ---- | --- | ----- | ---------------------- |
| 3.1 Fan-out tests | Added `test_fan_out.py` covering specialist scheduling, non-canceling failure behavior, and timeout propagation. | `arun_multi_agent_review()` invokes Bug Team, Security, and Cross-Repo runners and passes configured timeout. | Async core was separated from sync wrapper to preserve public sync API. |
| 3.2 Judge tests | Added `test_judge.py` covering duplicate collapse, severity escalation, distinct findings, deterministic behavior, and BugReport-shaped dicts. | Implemented `_run_judge()` deterministic dedupe over Bug A/B `SpecialistBugOutput`. | Dedupe key excludes severity so same-location severity conflicts can escalate. |
| 3.3 Synthesizer tests | Added `test_synthesizer.py` covering merge of judged + security bugs, duplicate prevention, approval logic, summary, `ReviewOutput` validation, and impact warnings. | Implemented `_synthesize()` returning valid `ReviewOutput`. | Approval is false for critical bugs or high impact warnings; empty clean result approves. |
| 3.4 Posting invariant tests | Added `test_posting_invariant.py` covering exactly-one post with bugs, no post without bugs, and no specialist posting tools. | `arun_multi_agent_review()` calls `post_review_comments()` once after synthesis when `result.bugs` is non-empty. | Posting remains orchestrator-only; specialists are built without tools/token. |
| 3.5 `_run_judge()` | N/A after RED tests. | Added deterministic judge/deduper helper. | Severity escalation implemented for duplicate keys. |
| 3.6 `_synthesize()` | N/A after RED tests. | Added final merge/synthesis helper. | Produces existing `ReviewOutput` contract. |
| 3.7 Complete orchestrator | Replaced fan-out stub coverage with async orchestration coverage. | Added `arun_multi_agent_review()` async core and `run_multi_agent_review()` sync wrapper via `_run_coro_sync()`. | Maintains current sync public boundary while allowing async fan-out internally; active-event-loop callers get explicit guidance to use `arun_multi_agent_review()`. |
| 3.8 Backend compatibility tests | Added `test_backend_compatibility.py` for `ReviewOutput`/backend response compatibility. | Tests preserve response-shape assumptions. | Backend API shape remains unchanged. |
| 3.9 Cleanup mono-agent helpers | Superseded mono-agent routing was removed/bypassed from public path. | `agent.py` now delegates public configured review flow to orchestrator while reusable helpers remain importable. | Old helper tests were updated where they asserted obsolete routing. |
| 3.10 Update mono-agent tests | Updated tests that depended on mono-agent internals. | Current tests target public routing/output behavior through the multi-agent seam. | External behavior coverage preserved. |
| 3.11 PR 3 gate | Task file marks full PR3 gate complete. | Working tree includes fan-out, judge, synthesizer, posting, cleanup, and backend compatibility tests. | Final proof still needs 3.12 commands before verify/archive. |

### PR 3 Files Changed

| File | Action | Notes |
| ---- | ------ | ----- |
| `src/reviewer/orchestrator.py` | Modified | Added async fan-out core, sync wrapper, judge, synthesizer, and exactly-once posting. |
| `src/reviewer/agent.py` | Modified | Public review path delegates to orchestrator; reusable helpers retained. |
| `src/reviewer/tests/test_fan_out.py` | Created | Fan-out orchestration tests. |
| `src/reviewer/tests/test_judge.py` | Created | Judge/deduper tests. |
| `src/reviewer/tests/test_synthesizer.py` | Created | Synthesis / `ReviewOutput` tests. |
| `src/reviewer/tests/test_posting_invariant.py` | Created | Exactly-once posting boundary tests. |
| `src/reviewer/tests/test_backend_compatibility.py` | Created | Backend/public response compatibility tests. |
| `src/reviewer/tests/test_agent.py` | Modified | Mono-agent assumptions updated or removed. |
| `src/reviewer/tests/test_review_integration.py` | Modified | Integration expectations adjusted for orchestrator path. |
| `src/reviewer/tests/test_review_pr_with_config.py` | Modified | Configured review tests target orchestrator seam. |
| `src/reviewer/tests/test_tools.py` | Modified | Tool tests kept compatible with posting/comment payload behavior. |

## Current State

### Completed

- PR 1 routing seam, context builder, internal contracts, prompts, and timeout config.
- PR 2 specialist runners for Bug A/B Team, Security Reviewer, and Cross-Repo Impact Reviewer.
- PR 3 async fan-out, judge/deduper, synthesizer, exactly-once posting boundary, sync wrapper, and test updates.
- Hybrid SDD mirror exists in Engram for OpenSpec artifacts.

### Remaining

- 3.12 Final integration check:
  - `uv run pytest`
  - `uv run ruff check .`
  - confirm no specialist agent receives `github_token` or `post_review_comments`
  - confirm `post_review_comments` call site is restricted to the final orchestrator posting boundary
  - confirm `ReviewOutput` validates end-to-end
  - confirm backend `ReviewResponse` fields remain populated
- `/sdd-verify multi-agent-pr-review`
- `/sdd-archive multi-agent-pr-review` if verification passes

## Deviations from Original Plan

- The initial PR1 stub was sync to preserve the existing public/backend call path. PR3 resolved this with `arun_multi_agent_review()` as the async core and `run_multi_agent_review()` as a sync wrapper.
- `test_review_pr_with_config.py` moved earlier than originally planned because old mono-agent assertions broke once routing changed.
- Bug Team extraction uses `member_responses` first, then `messages`, because real and mocked Agno Team responses expose member output differently.

## Verification Fixes Batch (post-verify-report)

### Fixes Applied

| # | Gap | Severity | Fix Location | What Changed |
|---|-----|----------|--------------|--------------|
| 1 | True fan-out concurrency | CRITICAL | `orchestrator.py:arun_multi_agent_review()` | Bug Team, Security, and Cross-Repo now all passed to a single `asyncio.gather(..., return_exceptions=True)` instead of awaiting Bug Team before starting the others. |
| 2 | Degraded fallback | CRITICAL | `orchestrator.py:arun_multi_agent_review()` | Bug Team exception → empty `SpecialistBugOutput` markers; Judge exception → `_parse_failure_result(ctx.impact_result)`; Synthesizer exception → same `_parse_failure_result()`. No unhandled exceptions propagate after PR fetch. |
| 3 | Approval logic | CRITICAL | `orchestrator.py:_synthesize()` | Removed `len(all_bugs) == 0` from `approved` computation. Now `approved = not has_critical and not has_high_impact`, so minor-only bugs are approved per SYN-004. |
| 4 | Cross-repo grounding | CRITICAL | `orchestrator.py:_ground_impact_warnings()` | New helper filters parsed `ImpactWarning` items: `changed_file` must be in `ctx.changed_paths`; if graph warnings exist, `changed_file` must also appear in graph evidence. Unsupported claims are logged and discarded. |
| 5 | Strengthen tests | WARNING | `test_fan_out.py`, `test_synthesizer.py`, `test_backend_compatibility.py` | Concurrency proven via event-based scheduling test; bug-team/judge/synth failure degradation directly asserted; minor-only approval added; backend compatibility now exercises real `run_review()` mapping by patching `review_pr_with_config()`. |

### TDD Cycle Evidence (Fixes)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| Fix 1 (concurrency) | `test_fan_out.py` | Unit | ✅ 22/22 | ✅ Written | ✅ Passed | ✅ Event-based concurrency proof | ✅ Clean |
| Fix 2 (degraded fallback) | `test_fan_out.py` | Unit | ✅ 22/22 | ✅ Written | ✅ Passed | ✅ Bug-team + judge + synth failure cases | ✅ Clean |
| Fix 3 (approval logic) | `test_synthesizer.py` | Unit | ✅ 22/22 | ✅ Written | ✅ Passed | ✅ Minor-only bugs case | ✅ Clean |
| Fix 4 (grounding) | `test_fan_out.py` | Unit | ✅ 22/22 | ✅ Written | ✅ Passed | ✅ Unsupported claim discarded | ✅ Clean |
| Fix 5 (backend mapping) | `test_backend_compatibility.py` | Unit | ✅ 22/22 | ✅ Written | ✅ Passed | ✅ Real mapping exercised | ✅ Clean |

### Verification Commands

```bash
# Full suite
uv run pytest -v
# → 273 passed in 2.80s

# Linter
uv run ruff check src/reviewer/orchestrator.py src/reviewer/tests/test_fan_out.py src/reviewer/tests/test_synthesizer.py src/reviewer/tests/test_backend_compatibility.py backend/services/reviewer.py
# → All checks passed
```

### Remaining

- `/sdd-verify multi-agent-pr-review` (re-run after fixes)
- `/sdd-archive multi-agent-pr-review` if verification passes

---

## Verify Gaps Fix Batch 2 (post-verify-report #2)

### Fixes Applied

| # | Gap | Severity | Fix Location | What Changed |
|---|---|---|---|---|
| 6 | Partial Bug Team failure isolation | CRITICAL | `orchestrator.py:_run_bug_reviewers()` | Missing reviewer outputs are replaced with empty `SpecialistBugOutput` markers instead of raising `RuntimeError`. Surviving output is preserved and reaches `_run_judge` / `_synthesize`. |
| 7 | Bug Team timeout enforcement | CRITICAL | `orchestrator.py:arun_multi_agent_review()` | Bug Team call wrapped in `asyncio.wait_for(..., timeout=Config.REVIEW_SPECIALIST_TIMEOUT_SECONDS)` inside the `gather`, consistent with Security/Cross-Repo. |
| 8 | Synthesizer summary contract | WARNING | `orchestrator.py:_synthesize()` | Summary now explicitly mentions security findings count, impact warnings count, and approval recommendation. |
| 9 | Strengthen tests / remove tautology | WARNING | `test_bug_team.py`, `test_fan_out.py`, `test_synthesizer.py`, `test_review_pr_with_config.py` | Added partial-failure, total-failure, timeout-degradation, and summary-coverage tests. Replaced tautological `assert True` with `mock_post.assert_not_called()`. |

### TDD Cycle Evidence (Fixes Batch 2)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| Fix 6 (partial failure) | `test_bug_team.py` | Unit | ✅ 32/32 | ✅ Written | ✅ Passed | ✅ Total failure + partial failure | ✅ Clean |
| Fix 6 (orchestrator proof) | `test_fan_out.py` | Unit | ✅ 32/32 | ✅ Written | ✅ Passed | ✅ Surviving bug reaches final output | ✅ Clean |
| Fix 7 (timeout) | `test_fan_out.py` | Unit | ✅ 32/32 | ✅ Written | ✅ Passed | ✅ Degrades instead of hanging | ✅ Clean |
| Fix 8 (summary) | `test_synthesizer.py` | Unit | ✅ 32/32 | ✅ Written | ✅ Passed | ✅ Clean + high-impact cases | ✅ Clean |
| Fix 9 (assert True) | `test_review_pr_with_config.py` | Unit | ✅ 32/32 | ✅ Written | ✅ Passed | — | ✅ Clean |

### Verification Commands

```bash
# Full suite
uv run pytest
# → 279 passed in 2.98s

# Linter
uv run ruff check .
# → All checks passed
```

### Status

All tasks complete. Ready for verify/archive.

---

## Verify Gaps Fix Batch 3 (post-verify-report #3 — final)

### Fixes Applied

| # | Gap | Severity | Fix Location | What Changed |
|---|---|---|---|---|
| 10 | Judge semantic dedupe | CRITICAL | `orchestrator.py:_run_judge()` | Dedupe key changed from `(file, line, description[:50].lower())` to `(file, line)`. Same-location/category duplicates from A/B now collapse even when wording differs. Severity escalation preserved. |
| 11 | Synthesizer bug/security overlap merge | CRITICAL | `orchestrator.py:_synthesize()` | Introduced `_merge_bug_dicts()` helper. Synthesizer now merges judged bugs and security findings by `(file, line)`, escalating to the higher severity and combining description/suggestion text. |

### TDD Cycle Evidence (Fixes Batch 3)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| Fix 10 (judge dedupe) | `test_judge.py` | Unit | ✅ 17/17 | ✅ Written | ✅ Passed | ✅ Same-line different wording + severity escalation | ✅ Clean |
| Fix 11 (synth overlap) | `test_synthesizer.py` | Unit | ✅ 20/20 | ✅ Written | ✅ Passed | ✅ Judged major + security critical at same location | ✅ Clean |

### Verification Commands

```bash
# Full suite
uv run pytest
# → 282 passed in 3.08s

# Linter
uv run ruff check .
# → All checks passed
```

### Status

All tasks complete. Ready for verify/archive.

---

## Judgment Day Round 1 Fixes

### Fixes Applied

| # | Issue | Severity | Fix Location | What Changed |
|---|---|---|---|---|
| 12 | Impact warning merge dedupe via whole-object equality | CRITICAL | `orchestrator.py:_merge_impact_warnings()` + `arun_multi_agent_review()` | Replaced `w not in impact_warnings` whole-object dedupe with semantic dedupe by `(changed_file, affected_service)`. When duplicates collide, severity escalates to the higher level. Graph + reviewer warnings now merged through this helper. |
| 13 | Judge dedupe by `(file, line)` merges different bugs on same line | CRITICAL | `orchestrator.py:_run_judge()` | Dedupe key changed from `(file, line)` to `(file, line, semantic_key)` where `semantic_key` is extracted from the description via `_bug_semantic_key()`. The helper skips common modifiers ("possible", "detected", etc.) and uses the first meaningful word (≥3 chars) as the category signal. Collapses wording variants (e.g., "Null pointer dereference detected" vs "Possible null reference at this location" both → "null") while preserving distinct bugs on the same line (e.g., "null pointer" vs "off-by-one"). |
| 14 | Cross-repo grounding validates changed_file but not affected_service/repo | CRITICAL | `orchestrator.py:_ground_impact_warnings()` | Graph evidence map now tracks `(affected_service, affected_repository)` tuples per `changed_file`. Parsed warnings with valid `changed_file` but unsupported `affected_service`/`affected_repository` are logged and discarded. |
| 15 | Broad specialist failure/timeout synthesizes approved=True "No bugs detected" | CRITICAL | `orchestrator.py:arun_multi_agent_review()` | Tracks `bug_failed`, `security_failed`, `cross_repo_failed` flags during normalization. If ALL three specialists failed, returns degraded `_parse_failure_result(ctx.impact_result)` with `approved=False` and `summary` starting with "Error:". Prevents misrepresenting a total failure as a clean approval. |

### TDD Cycle Evidence (Judgment Day Round 1)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| Fix 12 (impact dedupe) | `test_fan_out.py` | Unit | ✅ 28/28 | ✅ Written | ✅ Passed | ✅ Reviewer medium + graph high → escalated high | ✅ Clean |
| Fix 13 (judge semantic) | `test_judge.py` | Unit | ✅ 28/28 | ✅ Written | ✅ Passed | ✅ Same-line different wording collapses, different bug types preserved | ✅ Clean |
| Fix 14 (service/repo grounding) | `test_fan_out.py` | Unit | ✅ 28/28 | ✅ Written | ✅ Passed | ✅ Valid file + unsupported svc/repo discarded | ✅ Clean |
| Fix 15 (all-failure degradation) | `test_fan_out.py` | Unit | ✅ 28/28 | ✅ Written | ✅ Passed | ✅ All three specialists fail → degraded ReviewOutput | ✅ Clean |

### Verification Commands

```bash
# Full suite
uv run pytest -v
# → 286 passed in 3.07s

# Linter
uv run ruff check .
# → All checks passed
```

### Status

Judgment Day Round 1 issues resolved. Ready for re-verify.
