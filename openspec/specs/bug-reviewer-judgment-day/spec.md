# Spec: Blind Bug Reviewer A/B — Judgment Day

## Summary

Bug reviews SHALL be produced by two independent Agno Agents (A and B) running in blind broadcast mode within an Agno Team. Neither reviewer SHALL see the other's output before a judge step. A judge SHALL compare, deduplicate, and select high-confidence bug findings. This pattern replaces the single-LLM bug detection from the mono-agent flow.

---

## Requirements

### BUG-001 — Blind broadcast: identical input, independent output

The Agno Team MUST provide identical PR context to Bug Reviewer A and Bug Reviewer B. Neither agent's intermediate output MUST be visible to the other agent before the judge phase. The team MUST NOT enable member-to-member message passing during the independent review phase.

**Rationale:** Reviewer independence is essential for the Judgment Day pattern to surface genuine consensus findings and filter out hallucinated noise.

#### Scenario: Identical context delivered to both reviewers

- **GIVEN** the orchestrator has prepared a prompt containing `pr_title`, `diff_content`, and optional graph impact section
- **WHEN** the Agno Team is assembled with Bug Reviewer A and Bug Reviewer B
- **THEN** both agents MUST receive the exact same prompt string
- **AND** no contextual difference (ordering, truncation, annotation) SHALL exist between the two inputs

#### Scenario: No cross-contamination during review

- **GIVEN** Bug Reviewer A produces its output first
- **WHEN** Bug Reviewer B is still generating its response
- **THEN** Bug Reviewer B MUST NOT receive Bug Reviewer A's output as input or context
- **AND** the Agno Team leader or broadcast mode MUST NOT inject one member's response into the other member's conversation

#### Scenario: Both outputs are structurally independent

- **GIVEN** both Bug Reviewers have completed
- **WHEN** their outputs are collected by the orchestrator
- **THEN** each output MUST be parseable into a list of projected `BugReport` items (or empty)
- **AND** each output MUST NOT contain references to the other reviewer's findings (e.g., "Reviewer A also found...")

---

### BUG-002 — Judge step: compare, deduplicate, select

After both Bug Reviewers complete, a judge agent SHALL receive both outputs and MUST produce a single consolidated list of bug findings. The judge MUST deduplicate findings that refer to the same file, line range, and bug category. The judge MUST select findings based on confidence, agreement between reviewers, and severity.

**Rationale:** Two reviewers will produce overlapping and sometimes conflicting findings. A deterministic or judge-mediated deduplication step prevents noise in the final review.

#### Scenario: Identical finding from both reviewers is deduplicated

- **GIVEN** Reviewer A reports: `{"file": "src/api.py", "line": 42, "severity": "major", "description": "null pointer deref"}`
- **AND** Reviewer B reports: `{"file": "src/api.py", "line": 42, "severity": "major", "description": "possible null dereference"}`
- **WHEN** the judge processes both outputs
- **THEN** exactly one bug SHALL appear in the consolidated output for `src/api.py:42`
- **AND** the description SHOULD combine or select the clearest phrasing

#### Scenario: Same file, different line, different bug — both kept

- **GIVEN** Reviewer A reports a bug at `src/api.py:42`
- **AND** Reviewer B reports a different bug at `src/api.py:87`
- **WHEN** the judge processes both outputs
- **THEN** both bugs SHALL appear in the consolidated output
- **AND** they MUST NOT be collapsed into a single finding

#### Scenario: Conflicting severity — judge resolves

- **GIVEN** Reviewer A reports a finding as `critical`
- **AND** Reviewer B reports the same finding as `minor`
- **WHEN** the judge processes both outputs
- **THEN** exactly one bug SHALL be emitted for that finding
- **AND** the severity SHALL be resolved by the judge's confidence assessment (escalate to higher severity when uncertain)

#### Scenario: Single-reviewer finding — included if confidence is high

- **GIVEN** Reviewer A reports a bug
- **AND** Reviewer B does not report the same bug
- **WHEN** the judge evaluates Reviewer A's finding
- **THEN** the finding MAY be included in consolidated output if the judge assesses high confidence
- **AND** a low-confidence, single-reviewer-only finding SHOULD be discarded

#### Scenario: No bugs found by either reviewer

- **GIVEN** Reviewer A reports no bugs
- **AND** Reviewer B reports no bugs
- **WHEN** the judge processes both empty outputs
- **THEN** the consolidated `bugs` list MUST be empty
- **AND** `approved` SHOULD evaluate to `true` (subject to security and cross-repo findings)

---

### BUG-003 — Bug Reviewer prompts are role-specific

Bug Reviewer A and Bug Reviewer B MUST receive a prompt that instructs them to focus on code-level bugs: logic errors, null dereferences, off-by-one errors, incorrect error handling, race conditions, and similar code defects. They MUST NOT be instructed to review security concerns or cross-repo impact.

**Rationale:** Separation of concerns between specialists prevents duplicated work and keeps each agent's output focused and parseable.

#### Scenario: Bug prompt excludes security review scope

- **GIVEN** the Bug Reviewer prompt is constructed
- **WHEN** it is inspected
- **THEN** it MUST include instructions to find code-level bugs
- **AND** it MUST explicitly exclude security vulnerability assessment
- **AND** it MUST explicitly exclude cross-repository impact reasoning

#### Scenario: Bug prompt references diff content

- **GIVEN** the Bug Reviewer prompt
- **WHEN** it is inspected
- **THEN** it MUST instruct the reviewer to analyze the provided `<diff_content>`
- **AND** it MUST reference the `<pr_title>` for context

---

### BUG-004 — Judge output is valid ReviewOutput-compatible

The judge's consolidated output MUST be directly usable by the synthesizer to produce the final `ReviewOutput`. The judge MUST NOT modify fields outside the bug list.

**Rationale:** The judge is a specialist in bug deduplication; the synthesizer owns the final `ReviewOutput` assembly.

#### Scenario: Judge output maps to BugReport list

- **GIVEN** the judge has processed both reviewers' outputs
- **WHEN** the judge returns its result
- **THEN** the result MUST be parseable into a `list[BugReport]`
- **AND** each `BugReport` MUST have valid `file`, `line`, `severity`, `description`, and `suggestion` fields
- **AND** `severity` MUST be one of `critical`, `major`, `minor`
