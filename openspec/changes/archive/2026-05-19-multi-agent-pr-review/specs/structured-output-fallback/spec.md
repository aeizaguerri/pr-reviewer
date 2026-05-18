# Spec: Structured-Output Fallback

## Summary

Each specialist agent and the judge MUST attempt structured output (via `output_schema` or equivalent) when the configured provider supports it. When the provider does not support structured output, or when parsing fails, the system MUST fall back to parsing JSON from raw text using the existing `json.loads` + Pydantic validation pattern. Cross-repo impact findings MUST still satisfy grounding requirements even under fallback.

---

## Requirements

### SOF-001 — Structured output attempted per specialist

Each specialist agent (Bug Reviewer A, Bug Reviewer B, Security Reviewer, Cross-Repo Impact Reviewer, judge) MUST be configured with `output_schema` when `supports_structured_output` is `True` for the active provider. The schema MUST match the expected output type for that specialist.

**Rationale:** Structured output improves parse reliability. The existing `_build_agent_with_config(supports_structured_output=...)` pattern should be reused per specialist.

#### Scenario: Specialist with structured-output provider

- **GIVEN** the provider config has `supports_structured_output=True`
- **WHEN** Bug Reviewer A is assembled
- **THEN** its agent MUST be created with `output_schema` set to its expected output model
- **AND** the same SHALL apply to Bug Reviewer B, Security Reviewer, Cross-Repo Impact Reviewer, and the judge

#### Scenario: Specialist with non-structured-output provider

- **GIVEN** the provider config has `supports_structured_output=False`
- **WHEN** any specialist is assembled
- **THEN** its agent MUST be created with `output_schema=None`
- **AND** the prompt MUST include formatting instructions to produce parseable JSON

---

### SOF-002 — Fallback parsing per specialist

When a specialist agent returns output that cannot be parsed as structured output, the orchestrator MUST attempt `json.loads()` on the raw response text. If that also fails, the specialist's output SHALL be treated as a failure (see `specialist-failure/spec.md`).

**Rationale:** The existing `json.loads` → Pydantic constructor pattern in `review_pr_with_config()` is the proven fallback. It should be applied per specialist.

#### Scenario: Successful JSON fallback

- **GIVEN** a specialist returns raw text containing valid JSON matching its expected schema
- **WHEN** structured output parsing fails but `json.loads(raw)` succeeds
- **THEN** the parsed result MUST be used as the specialist's output
- **AND** the specialist SHALL be considered to have completed successfully

#### Scenario: Failed JSON fallback

- **GIVEN** a specialist returns raw text that is not valid JSON
- **WHEN** both structured output parsing and `json.loads()` fail
- **THEN** the specialist SHALL be marked as failed
- **AND** specialist failure handling SHALL apply (see `specialist-failure/spec.md`)

#### Scenario: JSON parses but Pydantic validation fails

- **GIVEN** `json.loads(raw)` returns a dict
- **WHEN** constructing the expected Pydantic model raises `ValidationError`
- **THEN** the specialist SHALL be marked as failed
- **AND** the raw response SHALL be logged using the existing `_log_full_llm_response` pattern when debug logging is enabled

---

### SOF-003 — Fallback preserves grounding for Cross-Repo Impact Reviewer

When the Cross-Repo Impact Reviewer operates under fallback parsing, its output MUST still satisfy the grounding requirement: impact claims MUST cite changed paths and existing `ImpactWarning` evidence. The orchestrator MUST validate this after parsing.

**Rationale:** The grounding constraint is a correctness requirement, not a structured-output convenience. It must hold regardless of parsing path.

#### Scenario: Fallback impact output validated for grounding

- **GIVEN** the Cross-Repo Impact Reviewer's output was parsed via JSON fallback
- **WHEN** the orchestrator validates the output
- **THEN** each `ImpactWarning`-shaped item MUST be checked against the available changed paths and graph evidence
- **AND** items that fail grounding MUST be discarded

---

### SOF-004 — Debug logging for parse failures

When any specialist's output fails to parse, the raw response MUST be logged using the existing `_log_full_llm_response()` pattern (file output when `PR_REVIEWER_LOG_RAW_LLM_FAILURES=true`, truncated preview otherwise).

**Rationale:** Debuggability. The existing pattern already covers this for the mono-agent path; it must extend to all specialists.

#### Scenario: Specialist parse failure logged

- **GIVEN** `PR_REVIEWER_LOG_RAW_LLM_FAILURES=true`
- **WHEN** Bug Reviewer A's output fails to parse
- **THEN** the full raw response MUST be written to `/tmp/pr-reviewer-logs/llm-fail-{owner}-{repo}-{pr_number}-bug-a.txt`
- **AND** the log path MUST distinguish which specialist failed

#### Scenario: Debug flag off — truncated preview

- **GIVEN** `PR_REVIEWER_LOG_RAW_LLM_FAILURES` is not set or is `false`
- **WHEN** any specialist's output fails to parse
- **THEN** a truncated preview (first 200 chars) MUST be emitted as a `logger.warning`
- **AND** no file SHALL be written
