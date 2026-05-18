# Spec: Strict TDD Verifiability

## Summary

All multi-agent orchestrator behavior SHALL be verifiable through automated tests using `uv run pytest`. The strict TDD discipline (RED, GREEN, TRIANGULATE, REFACTOR) SHALL be followed. Tests MUST cover routing, blind broadcast, deduplication, specialist failure isolation, exactly-once posting, and cross-repo grounding.

---

## Requirements

### TDD-001 — Test runner and strict TDD mode

The test suite SHALL pass with `uv run pytest` after every implementation increment. Strict TDD mode is active: implementation code SHALL NOT be written before a failing test.

**Rationale:** The project's `openspec/config.yaml` declares `strict_tdd: true` with `uv run pytest`. This spec ensures the multi-agent change adheres to that contract.

#### Scenario: All tests pass before merge

- **GIVEN** the feature branch for `multi-agent-pr-review`
- **WHEN** `uv run pytest` is executed
- **THEN** all 225+ collected tests MUST pass (with integration tests skipped by default)
- **AND** new tests for multi-agent behavior MUST be present and passing

#### Scenario: RED phase before implementation

- **GIVEN** a new requirement is being implemented
- **WHEN** work begins on that requirement
- **THEN** at least one failing test MUST exist before production code is written
- **AND** the test MUST fail for the right reason (asserting the new behavior, not a syntax error)

---

### TDD-002 — Primary multi-agent routing coverage

Tests MUST verify that `review_pr_with_config()` routes through the multi-agent orchestrator and that no mono-agent fallback path is reachable.

#### Scenario: review_pr_with_config delegates to orchestrator

- **GIVEN** a mock orchestrator function
- **WHEN** `review_pr_with_config()` is called
- **THEN** the mock orchestrator MUST be invoked
- **AND** the legacy `_build_agent` → `_run_llm` single-agent path MUST NOT execute

#### Scenario: No runtime feature flag controls routing

- **GIVEN** the codebase after migration
- **WHEN** a test inspects the routing logic
- **THEN** there MUST NOT be an `if multi_agent_enabled:` branch that selects between mono-agent and multi-agent paths
- **AND** the multi-agent orchestrator MUST be the only path

---

### TDD-003 — Blind Bug Reviewer A/B testability

Tests MUST verify that Bug Reviewer A and Bug Reviewer B receive identical input and that neither sees the other's output.

#### Scenario: Identical input verified

- **GIVEN** a test that provides a known PR context
- **WHEN** Bug Reviewer A and Bug Reviewer B are invoked (mocked or real)
- **THEN** the input prompt to both MUST be byte-identical
- **AND** no ordering, truncation, or annotation difference SHALL exist

#### Scenario: No cross-contamination

- **GIVEN** Bug Reviewer A is configured to produce output X
- **AND** Bug Reviewer B is configured to produce output Y
- **WHEN** the Agno Team executes
- **THEN** Bug Reviewer B's input MUST NOT contain X
- **AND** Bug Reviewer A's input MUST NOT contain Y

---

### TDD-004 — Judge deduplication testability

Tests MUST verify that the judge correctly collapses duplicate findings, preserves distinct findings, and handles edge cases (empty input, single-reviewer findings).

#### Scenario: Duplicate collapse

- **GIVEN** Reviewer A output: `[BugReport(file="a.py", line=1, ...)]`
- **AND** Reviewer B output: `[BugReport(file="a.py", line=1, ...)]`
- **WHEN** the judge processes both
- **THEN** the output MUST contain exactly one `BugReport` for `a.py:1`

#### Scenario: Distinct findings preserved

- **GIVEN** Reviewer A: bug at `a.py:1`; Reviewer B: bug at `b.py:5`
- **WHEN** the judge processes
- **THEN** the output MUST contain both bugs

#### Scenario: Empty inputs

- **GIVEN** both reviewers return empty bug lists
- **WHEN** the judge processes
- **THEN** the output MUST be an empty bug list

---

### TDD-005 — Specialist failure isolation testability

Tests MUST verify that a failed specialist does not corrupt the overall result and that other specialists still contribute.

#### Scenario: Bug Reviewer A fails, B succeeds

- **GIVEN** Bug Reviewer A raises an exception
- **AND** Bug Reviewer B returns valid bugs
- **WHEN** the orchestrator collects results
- **THEN** Bug Reviewer B's bugs MUST appear in the final `ReviewOutput`
- **AND** the orchestrator MUST NOT return a `_parse_failure_result` degraded output (because B succeeded)

#### Scenario: All bug reviewers fail

- **GIVEN** Bug Reviewer A and Bug Reviewer B both fail
- **WHEN** the orchestrator synthesizes
- **THEN** the final `bugs` list MUST be empty or contain only Security Reviewer findings
- **AND** a valid `ReviewOutput` MUST still be returned

---

### TDD-006 — Exactly-once posting testability

Tests MUST verify that `post_review_comments()` is called at most once per review, only from the orchestrator, and only after synthesis. Tests MUST verify that specialist agents do not have posting capability.

#### Scenario: Single post_review_comments call

- **GIVEN** a review produces bugs
- **WHEN** the orchestrator completes
- **THEN** `post_review_comments` MUST be called exactly once
- **AND** the call arguments MUST match the synthesized `ReviewOutput`

#### Scenario: No posting when no bugs

- **GIVEN** the final synthesized `ReviewOutput` has an empty `bugs` list
- **WHEN** the orchestrator completes
- **THEN** `post_review_comments` MUST NOT be called

#### Scenario: Specialists cannot call post_review_comments

- **GIVEN** each specialist agent's tool configuration
- **WHEN** inspected
- **THEN** no specialist SHALL have `post_review_comments` in its tool list

---

### TDD-007 — Cross-repo grounding testability

Tests MUST verify that unsupported impact claims are discarded and that valid impact claims are preserved.

#### Scenario: Unsupported claim discarded

- **GIVEN** the Cross-Repo Impact Reviewer output contains a claim for `service-x`
- **AND** no graph `ImpactWarning` exists for `service-x`
- **AND** no changed file path logically connects to `service-x`
- **WHEN** the grounding validator runs
- **THEN** the claim for `service-x` MUST be removed from `impact_warnings`

#### Scenario: Valid claim preserved

- **GIVEN** the Cross-Repo Impact Reviewer output contains a claim for `service-y`
- **AND** a graph `ImpactWarning` exists linking a changed file to `service-y`
- **WHEN** the grounding validator runs
- **THEN** the claim for `service-y` MUST be preserved in `impact_warnings`

---

### TDD-008 — Public response shape compatibility

Tests MUST verify that the backend service returns `ReviewResponse` with all expected fields, and that `ReviewOutput` validation passes for all synthesis paths.

#### Scenario: ReviewResponse fields present

- **GIVEN** a valid `ReviewRequest`
- **WHEN** `run_review()` returns
- **THEN** the result MUST be an instance of `ReviewResponse`
- **AND** `summary` MUST be a non-empty string
- **AND** `approved` MUST be a boolean
- **AND** `bugs` MUST be a list of `BugReportResponse`
- **AND** `impact_warnings` MUST be a list of `ImpactWarningResponse`

#### Scenario: ReviewOutput validation passes

- **GIVEN** the synthesizer's output dict
- **WHEN** `ReviewOutput(**output_dict)` is called
- **THEN** no `ValidationError` SHALL be raised

---

### TDD-009 — Superseded mono-agent tests updated

Tests that assert mono-agent internals (e.g., `_build_agent` called directly from `review_pr`, single `_run_llm` invocation, specific mono-agent prompt structure) SHALL be updated or removed. External behavior coverage SHALL be preserved through the new multi-agent path.

#### Scenario: No mono-agent-specific test failures

- **GIVEN** the full test suite
- **WHEN** `uv run pytest` is executed
- **THEN** no test SHALL fail because it asserts mono-agent-only internals
- **AND** tests that verified external behavior (response shape, posting, graph enrichment) MUST still pass through the multi-agent path
