# Proposal: multi-agent-pr-review

## Intent

Evolve `pr-reviewer` from a mono-agent PR review flow into a multi-agent review architecture as the next active iteration of the product.

The approved direction is **Hybrid Orchestrator + Agno Team**:

- a local internal orchestrator owns data flow, error handling, synthesis, and side effects;
- an Agno Team runs blind Bug Reviewer A/B using a broadcast / Judgment Day pattern;
- Security Reviewer and Cross-Repo Impact Reviewer run in parallel as specialist reviewers;
- a judge/deduper/synthesizer consolidates specialist findings into the existing `ReviewOutput` model;
- GitHub posting remains a single final side effect and happens exactly once.

## Scope

### In Scope

- Replace the mono-agent review path with a multi-agent orchestrator as the primary review flow.
- Remove legacy mono-agent routing where it is no longer needed.
- Keep existing backend entrypoints usable by current callers unless a later spec explicitly changes the API.
- Use Agno Team for blind Bug Reviewer A/B fan-out:
  - both reviewers receive the same PR context independently;
  - reviewers must not see or condition on each other's outputs;
  - a judge step compares, deduplicates, and selects high-confidence bug findings.
- Run Security Reviewer in parallel to identify security-relevant review findings from the same PR context.
- Run Cross-Repo Impact Reviewer in parallel using existing changed-path and graph/impact-warning context only.
- Add a judge/deduper/synthesizer phase that emits the existing `ReviewOutput` shape.
- Keep `post_review_comments()` or equivalent GitHub posting logic outside subagents and invoke it once after final synthesis.
- Add strict TDD coverage for flag gating, fan-out orchestration, structured-output parsing, deduplication, fallback, and exactly-once posting.

### Non-Goals

- No autonomous GitHub posting by any specialist reviewer or Agno Team member.
- No broad rewrite of PR fetching, GitHub posting, backend adapters, or graph enrichment beyond what is required for the new flow.
- No feature-flagged fallback to the mono-agent implementation.
- No requirement to preserve internal mono-agent builders/prompts if the multi-agent design supersedes them.
- No API response shape change unless explicitly approved in a later change.

## Affected Areas

- `backend/core/config.py`
  - Remove any need for a multi-agent opt-in flag; keep provider and graph configuration focused on the new flow.
- `backend/services/reviewer.py`
  - Continue returning the existing `ReviewResponse` shape.
  - Route through the existing review service contract without exposing multi-agent internals.
- `src/reviewer/agent.py`
  - Route `review_pr_with_config()` through the multi-agent orchestrator.
  - Remove or simplify mono-agent-only orchestration once replaced.
- `src/reviewer/models.py`
  - Preserve `BugReport` and `ReviewOutput` public contracts.
  - Add internal-only specialist result models only if needed.
- `src/reviewer/prompts.py`
  - Add role-specific prompts for Bug Reviewer A/B, Security Reviewer, Cross-Repo Impact Reviewer, and judge/synthesizer.
  - Constrain cross-repo impact reasoning to available impact evidence.
- `src/reviewer/tools.py`
  - Preserve PR fetching and exactly-once final GitHub posting behavior.
- `backend/tests`, `src/reviewer/tests`
  - Add tests for strict TDD evidence across routing, orchestration, synthesis, and side-effect boundaries.

## Proposed Behavior

1. Existing caller invokes `review_pr_with_config()` or the backend review service as it does today.
2. The review flow fetches PR data and graph enrichment once.
3. Bug Reviewer A/B receive the same context through an Agno Team broadcast/Judgment Day pattern.
4. Security Reviewer and Cross-Repo Impact Reviewer run in parallel with the bug-review path.
5. Specialist outputs are normalized into internal result structures.
6. Judge/deduper/synthesizer produces one final review result.
7. Final GitHub review posting is executed exactly once, after synthesis, through the existing posting boundary.
8. The caller receives the current response shape unless a future approved API change says otherwise.

## Risks and Mitigations

- **Increased cost and latency**
  - Mitigation: run specialists in parallel where safe; keep prompts focused; measure before adding more reviewers.
- **Provider structured-output inconsistencies**
  - Mitigation: reuse current parsing/fallback patterns; validate each specialist output before synthesis.
- **Bug Reviewer A/B contamination**
  - Mitigation: enforce blind broadcast semantics; do not share intermediate member outputs until judge phase.
- **Duplicate or noisy findings**
  - Mitigation: add judge/deduper rules keyed by file, line/range, category, and semantic similarity.
- **Autonomous or duplicate GitHub posting**
  - Mitigation: keep posting out of all subagents; unit-test that final posting is invoked once and only once.
- **Cross-repo impact hallucination**
  - Mitigation: require impact findings to cite changed paths and existing impact-warning/graph context; otherwise downgrade or discard.
- **Regression in public API consumers**
  - Mitigation: keep the current response shape for this iteration unless explicitly changed; add regression tests around the backend response.
- **Review workload / large diff risk**
  - Mitigation: keep implementation incremental and split if tasks predict more than ~400 changed lines.

## Rollback Plan

- Roll back by reverting the multi-agent orchestration change set from version control.
- Keep implementation split into reviewable work units so rollback can target the orchestration layer without touching unrelated modules.
- If the new flow is unstable during development, fix forward or temporarily revert the affected commit; do not maintain a runtime mono-agent fallback.

## Success Criteria

- The multi-agent orchestrator is the primary review path.
- Backend/API callers continue receiving the current response shape for this iteration.
- The orchestrator produces a valid final review result from specialist outputs.
- Bug Reviewer A/B operate blindly and are judged/deduplicated after independent review.
- Security and Cross-Repo Impact reviewers execute in parallel with the bug-review path.
- GitHub posting occurs exactly once per review request and only after final synthesis.
- Subagents/specialist reviewers cannot post GitHub comments directly.
- Cross-repo impact findings are grounded in available changed-path and impact-warning/graph context.
- The full configured test command passes: `uv run pytest`.
- Linting remains clean with the configured Ruff command: `uv run ruff check .`.

## Test Strategy

Strict TDD is active for this project. Implementation should follow RED, GREEN, TRIANGULATE, REFACTOR using `uv run pytest`.

Required coverage:

- **Primary multi-agent routing**
  - `review_pr_with_config()` calls the multi-agent orchestrator;
  - no runtime feature flag is required to select the mono-agent path;
  - mono-agent-only routing is removed or bypassed.
- **Public response compatibility**
  - `review_pr_with_config()` still returns `ReviewOutput`;
  - backend service still returns the existing `ReviewResponse` shape.
- **Blind Bug Reviewer A/B**
  - both reviewers receive identical PR context;
  - neither reviewer receives the other's output before judge phase.
- **Parallel specialist orchestration**
  - Security Reviewer and Cross-Repo Impact Reviewer are scheduled alongside bug-review flow;
  - failures in one specialist are handled according to the chosen fallback policy without corrupting final output.
- **Judge/deduper/synthesizer**
  - duplicate findings collapse into a single `BugReport`;
  - conflicting or low-confidence findings are handled deterministically;
  - synthesized output validates against existing `ReviewOutput`.
- **Exactly-once posting**
  - posting is not available to specialist reviewers;
  - final posting function is called once after synthesis;
  - no posting occurs if the existing flow mode/config says not to post.
- **Cross-repo impact grounding**
  - impact findings require existing graph/impact-warning evidence;
  - unsupported impact claims are discarded or downgraded.
- **Superseded mono-agent behavior**
  - tests that assumed mono-agent internals are updated or removed;
  - externally relevant behavior is covered through the new multi-agent path.
