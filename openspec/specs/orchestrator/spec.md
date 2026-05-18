# Spec: Multi-Agent Orchestrator

## Summary

The multi-agent orchestrator SHALL be the primary and only review path. It MUST replace the mono-agent flow entirely; no runtime feature flag, default-off mode, or legacy mono-agent fallback SHALL exist. The orchestrator MUST coordinate data flow, error handling, synthesis, and side effects using a Hybrid Orchestrator + Agno Team pattern.

---

## Requirements

### ORCH-001 — Multi-agent orchestrator is the primary review path

The `review_pr_with_config()` function MUST route through the multi-agent orchestrator. No runtime feature flag or configuration toggle SHALL exist to select the mono-agent path. There MUST NOT be a legacy mono-agent fallback.

**Rationale:** This is a live product iteration that supersedes the mono-agent flow. Preserving a fallback adds unreviewed complexity and dilutes test coverage.

#### Scenario: Caller invokes review_pr_with_config

- **GIVEN** a caller invokes `review_pr_with_config(owner, repo, pr_number, provider_config, github_token)`
- **WHEN** the function executes
- **THEN** it MUST delegate to the multi-agent orchestrator
- **AND** the orchestrator MUST be the only execution path
- **AND** no code path SHALL route to the legacy mono-agent `_build_agent` / `_run_llm` single-agent call

#### Scenario: No mono-agent routing code remains

- **GIVEN** the codebase after migration
- **WHEN** a grep for legacy mono-agent orchestration is performed
- **THEN** `_run_llm` MUST NOT be called directly from `review_pr` or `review_pr_with_config` outside the orchestrator's internal specialist agent runs
- **AND** the legacy mono-agent inline prompt building + single-LLM-call pattern SHALL be unreachable from the public review entrypoints

---

### ORCH-002 — Hybrid Orchestrator + Agno Team pattern

The orchestrator MUST use a Hybrid Orchestrator that owns contracts, errors, synthesis, and side effects, while delegating blind Bug Reviewer A/B to an Agno Team using a broadcast / Judgment Day pattern.

**Rationale:** Aligns with the user's preference for Team-based review while preserving deterministic error handling and side-effect control in the orchestrator.

#### Scenario: Agno Team runs Bug Reviewer A/B in blind broadcast mode

- **GIVEN** the orchestrator has fetched and enriched PR data
- **WHEN** bug review is triggered
- **THEN** an Agno Team SHALL be assembled with exactly two reviewer members (A and B)
- **AND** both members MUST receive identical PR context (diff, title, enrichment data)
- **AND** neither member MUST receive the other's intermediate output before the judge phase
- **AND** the team leader or broadcast mode MUST NOT share member-to-member interactions during the independent review phase

#### Scenario: Orchestrator retains control of side effects

- **GIVEN** the Agno Team produces bug review outputs
- **WHEN** the team run completes
- **THEN** the orchestrator MUST own the judge, deduplication, synthesis, and GitHub posting steps
- **AND** the Agno Team MUST NOT have access to `post_review_comments`
- **AND** the Agno Team MUST NOT directly modify the final `ReviewOutput`

---

### ORCH-003 — Data flow: single PR fetch and enrichment

The orchestrator MUST fetch PR data and run graph enrichment exactly once per review request, before any specialist reviewer is invoked. The results MUST be shared as context to all specialists.

**Rationale:** Avoids duplicate GitHub API calls and Neo4j queries, keeping cost and latency bounded.

#### Scenario: Single fetch per review

- **GIVEN** a valid `(owner, repo, pr_number)` tuple
- **WHEN** the orchestrator begins a review
- **THEN** `fetch_pr_data()` MUST be called exactly once
- **AND** `_enrich_with_graph()` (or equivalent) MUST be called at most once
- **AND** no specialist reviewer SHALL independently fetch PR data from GitHub

#### Scenario: Shared context distribution

- **GIVEN** PR data and enrichment have been fetched
- **WHEN** specialists (Bug Reviewer A, Bug Reviewer B, Security Reviewer, Cross-Repo Impact Reviewer) are invoked
- **THEN** all specialists MUST receive the identical enriched prompt context
- **AND** no specialist SHALL receive a subset that excludes graph enrichment when it is available

---

### ORCH-004 — Parallel specialist execution

The Security Reviewer and Cross-Repo Impact Reviewer MUST execute in parallel with the Bug Reviewer A/B path. The orchestrator MUST schedule all specialists concurrently and collect their results before synthesis.

**Rationale:** Parallelism mitigates latency from adding multiple specialist reviewers.

#### Scenario: Concurrent specialist fan-out

- **GIVEN** the orchestrator has prepared the shared PR context
- **WHEN** review execution begins
- **THEN** Bug Reviewer A/B (via Agno Team), Security Reviewer, and Cross-Repo Impact Reviewer MUST start concurrently
- **AND** the orchestrator MUST wait for all specialist results (or timeouts) before proceeding to synthesis
- **AND** the total wall-clock time SHOULD approximate the slowest specialist, not the sum

#### Scenario: Specialist collects only its own output

- **GIVEN** specialists are running in parallel
- **WHEN** any specialist completes
- **THEN** its output MUST be collected by the orchestrator
- **AND** no specialist SHALL receive another specialist's output during execution

---

### ORCH-005 — Public response shape preservation

The orchestrator MUST preserve the existing `ReviewOutput` Pydantic model as the return type of `review_pr_with_config()` and `review_pr()`. The backend service MUST continue returning `ReviewResponse` with fields `summary`, `approved`, `bugs`, and `impact_warnings`.

**Rationale:** Backward compatibility for existing API callers until a future approved API change explicitly alters the response shape.

#### Scenario: review_pr_with_config returns ReviewOutput

- **GIVEN** a multi-agent review completes successfully
- **WHEN** `review_pr_with_config()` returns
- **THEN** the return value MUST be an instance of `ReviewOutput`
- **AND** it MUST have non-empty `summary`, boolean `approved`, and list `bugs`
- **AND** `impact_warnings` MUST be populated from graph enrichment when available

#### Scenario: Backend ReviewResponse shape unchanged

- **GIVEN** the FastAPI backend receives a valid `ReviewRequest`
- **WHEN** `run_review()` executes through the multi-agent orchestrator
- **THEN** the HTTP response body MUST deserialize into `ReviewResponse`
- **AND** fields `summary`, `approved`, `bugs`, `impact_warnings` MUST all be present with correct types
- **AND** no new mandatory top-level fields SHALL appear in the response without an approved API change
