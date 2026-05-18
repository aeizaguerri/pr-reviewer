# Spec: Specialist Failure Handling

## Summary

The orchestrator MUST handle failures from any individual specialist without corrupting the final `ReviewOutput`. A failed specialist SHALL contribute an empty, degraded, or fallback result to the synthesis pipeline. The orchestrator MUST log the failure and MUST NOT crash, hang, or produce an invalid `ReviewOutput`.

---

## Requirements

### FAIL-001 — Isolated specialist failures

A failure in Bug Reviewer A, Bug Reviewer B, Security Reviewer, or Cross-Repo Impact Reviewer MUST NOT prevent other specialists from completing. A failure in one specialist MUST NOT cause the orchestrator to abort the entire review.

**Rationale:** Naive `asyncio.gather` with no exception handling would cancel other tasks. The orchestrator must isolate failures.

#### Scenario: Bug Reviewer A fails, Bug Reviewer B succeeds

- **GIVEN** Bug Reviewer A raises an exception or returns unparseable output
- **AND** Bug Reviewer B completes successfully with valid bug findings
- **WHEN** the orchestrator collects results
- **THEN** Bug Reviewer B's output MUST be used for the judge phase
- **AND** Bug Reviewer A's failure MUST be logged
- **AND** the orchestrator MUST NOT crash

#### Scenario: Both Bug Reviewers fail

- **GIVEN** Bug Reviewer A and Bug Reviewer B both fail
- **WHEN** the orchestrator collects results
- **THEN** the judge phase MUST receive two empty/failure markers
- **AND** the final `bugs` list MAY be empty or contain only Security Reviewer findings
- **AND** the orchestrator MUST still produce a valid `ReviewOutput` with a summary explaining the degradation

#### Scenario: Security Reviewer fails

- **GIVEN** the Security Reviewer fails
- **WHEN** the synthesizer assembles the final output
- **THEN** the `bugs` list MUST contain only judge-consolidated bug findings
- **AND** the summary SHOULD note that security review was unavailable
- **AND** `approved` MUST be computed from available data only

#### Scenario: Cross-Repo Impact Reviewer fails

- **GIVEN** the Cross-Repo Impact Reviewer fails
- **WHEN** the synthesizer assembles the final output
- **THEN** `impact_warnings` MUST contain only graph-derived warnings (if any)
- **AND** the summary MAY note that cross-repo impact analysis was unavailable

---

### FAIL-002 — Judge/synthesizer failure is fatal

If the judge or synthesizer fails, the orchestrator MUST produce a degraded `ReviewOutput` using the existing `_parse_failure_result()` pattern: `summary="Error: Agent failed to produce valid output."`, `bugs=[]`, `approved=False`. Graph-derived `impact_warnings` MUST still be attached if available.

**Rationale:** The judge and synthesizer are the final consolidation points. If they fail, there is no valid bug list to post. The system must degrade gracefully rather than crash.

#### Scenario: Judge fails

- **GIVEN** Bug Reviewers produced valid outputs
- **AND** the judge fails to produce a consolidated bug list
- **WHEN** the orchestrator handles the failure
- **THEN** the final `ReviewOutput` MUST have `summary="Error: Agent failed to produce valid output."`
- **AND** `bugs` MUST be empty
- **AND** `approved` MUST be `False`
- **AND** `impact_warnings` MUST contain graph-derived warnings if available
- **AND** no GitHub posting SHALL occur (empty bugs list)

#### Scenario: Synthesizer fails

- **GIVEN** the judge produced a valid bug list
- **AND** the synthesizer fails during final assembly
- **WHEN** the orchestrator handles the failure
- **THEN** the same `_parse_failure_result()` fallback SHALL be used
- **AND** the return type MUST still be `ReviewOutput`

---

### FAIL-003 — Timeout handling per specialist

Each specialist agent SHALL have a configurable timeout. If a specialist exceeds its timeout, it MUST be treated as a failure. The orchestrator MUST NOT wait indefinitely.

**Rationale:** LLM calls can hang. A stuck specialist should not block the entire review pipeline.

#### Scenario: Specialist times out

- **GIVEN** the Security Reviewer has a 120-second timeout
- **AND** the Security Reviewer does not complete within 120 seconds
- **WHEN** the timeout fires
- **THEN** the Security Reviewer SHALL be marked as failed
- **AND** the orchestrator MUST proceed with the remaining specialist results
- **AND** the timeout MUST be logged as a warning

#### Scenario: All specialists time out

- **GIVEN** every specialist exceeds its timeout
- **WHEN** the orchestrator collects results
- **THEN** the final output MUST be a degraded `ReviewOutput` via `_parse_failure_result()`
- **AND** the orchestrator MUST NOT crash or hang

---

### FAIL-004 — Orchestrator always returns ReviewOutput

Under no circumstances SHALL the orchestrator raise an unhandled exception to the caller of `review_pr_with_config()` or `review_pr()`. It MUST always return a `ReviewOutput` instance.

**Rationale:** The existing contract is that `review_pr_with_config()` returns `ReviewOutput`. Upstream callers (backend service, Streamlit UI) do not expect exceptions.

#### Scenario: Catastrophic failure → degraded ReviewOutput

- **GIVEN** an unexpected exception occurs at any point after PR data is fetched
- **WHEN** the orchestrator catches it
- **THEN** it MUST return `ReviewOutput(summary="Error: ...", bugs=[], approved=False, impact_warnings=...)`
- **AND** graph-derived `impact_warnings` SHALL be attached if already fetched
- **AND** the exception MUST be logged

#### Scenario: PR fetch failure

- **GIVEN** `fetch_pr_data()` raises an exception (e.g., network error, invalid PR)
- **WHEN** the orchestrator handles it
- **THEN** it MAY re-raise or return a degraded `ReviewOutput`, but the behavior MUST be consistent with the existing error contract for `review_pr_with_config()`
