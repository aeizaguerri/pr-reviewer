# Exploration: multi-agent-pr-review

## Current State

The codebase is a mono-agent Agno review system with a clean separation: `src/reviewer/agent.py` orchestrates fetch → enrich → prompt → LLM → parse → post. The `ReviewOutput` Pydantic model and `review_pr_with_config()` function are the key public contracts. GitHub posting happens as one final side effect through `post_review_comments()`.

## Affected Areas

- `src/reviewer/agent.py` — current linear review orchestration and LLM parsing.
- `src/reviewer/models.py` — public `BugReport` and `ReviewOutput` contracts to preserve.
- `src/reviewer/tools.py` — PR fetching and final GitHub review posting.
- `src/reviewer/prompts.py` — current reviewer prompt and graph impact prompt section.
- `backend/services/reviewer.py` — API/domain adapter that must keep returning `ReviewResponse`.
- `backend/core/config.py` — feature flag and provider configuration location.
- `backend/tests`, `src/reviewer/tests` — strict TDD coverage for flag gating, orchestration, parsing, and single posting.

## Approaches

1. **Agno Team first** — Use an Agno Team to coordinate all specialist reviewers.
   - Pros: matches the user mental model; built-in team abstraction; good for role-based review.
   - Cons: less deterministic if the team leader synthesizes too much; harder to test individual gates.
   - Effort: Medium.

2. **Agno Workflow** — Model review as explicit workflow steps with parallel fan-out.
   - Pros: clear pipeline, formal step graph, good fit for stable phases.
   - Cons: more boilerplate now; less aligned with the desired “team of reviewers” framing.
   - Effort: Medium/High.

3. **Custom orchestrator with parallel Agents** — Own orchestration with `asyncio.gather`, use Agno Agents per role.
   - Pros: most deterministic and testable; easy feature flag/fallback; preserves side-effect control.
   - Cons: less direct use of Team abstraction; more local orchestration code.
   - Effort: Medium.

4. **Hybrid Orchestrator + Agno Team** — Local orchestrator controls contracts, errors, synthesis, and posting; Agno Team handles blind Bug Reviewer A/B; Security and Cross-Repo Impact run in parallel as specialist agents.
   - Pros: best alignment with user preference for Teams + Judgment Day; preserves determinism and testability; keeps public API unchanged.
   - Cons: still increases latency/cost; requires careful structured-output handling per specialist.
   - Effort: Medium.

## Recommendation

Use **Hybrid Orchestrator + Agno Team** as the new primary review architecture. The orchestrator should run a fan-out where Bug Reviewer A and Bug Reviewer B are blind members of an Agno Team in broadcast mode, while Security Reviewer and Cross-Repo Impact Reviewer run in parallel. A judge/deduper/synthesizer consolidates outputs into the final review result. Keep `post_review_comments()` outside all agents and execute it exactly once at the end.

## Risks

- Structured output may not be supported by all providers; reuse the current fallback strategy per specialist.
- LLM cost/latency can increase significantly; mitigate with parallelism, focused prompts, and measured reviewer count.
- Bug reviewers must remain blind; configure Team to avoid sharing member interactions.
- Cross-repo impact reviewer must not invent graph evidence; it should only reason from changed paths and existing `ImpactWarning` data.
- Review workload is medium-high; split implementation if diff exceeds 400 lines.

## Ready for Proposal

Yes. Write proposal for `multi-agent-pr-review` with scope, non-goals, rollout, contracts, test plan, and rollback. The mono-agent flow is superseded rather than preserved as a runtime fallback.
