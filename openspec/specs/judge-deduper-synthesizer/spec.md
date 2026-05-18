# Spec: Judge, Deduper, and Synthesizer

## Summary

A judge/deduper/synthesizer phase SHALL consolidate all specialist outputs into a single `ReviewOutput`. The judge SHALL deduplicate Bug Reviewer A/B findings. The synthesizer SHALL merge bug findings from the judge with Security Reviewer findings, attach Cross-Repo Impact Reviewer findings as `impact_warnings`, and produce the final `ReviewOutput` compatible with the existing response shape.

---

## Requirements

### SYN-001 — Judge deduplicates Bug Reviewer A/B findings

The judge agent MUST receive the raw outputs of Bug Reviewer A and Bug Reviewer B. It MUST produce a single deduplicated `list[BugReport]` with duplicates collapsed and conflicts resolved.

**Rationale:** Covered in detail in `bug-reviewer-judgment-day/spec.md`. This spec addresses the judge's integration into the broader synthesis pipeline.

#### Scenario: Judge output feeds into synthesis

- **GIVEN** the judge has produced a deduplicated bug list
- **WHEN** the synthesizer receives it
- **THEN** the synthesizer MUST use the judge's bug list as the primary bug input
- **AND** the original raw Reviewer A/B outputs MUST NOT bypass the judge

---

### SYN-002 — Synthesizer merges Security Reviewer findings

The synthesizer MUST append Security Reviewer findings to the deduplicated bug list. If a Security finding has the same `(file, line)` as a judge-produced bug, the synthesizer MUST merge or escalate it (keeping at most one entry per file/line).

**Rationale:** Security findings and general bugs both populate the `bugs` list in `ReviewOutput`. Duplicate file/line entries are confusing.

#### Scenario: Security finding with no overlap

- **GIVEN** the judge produced bugs at `src/api.py:42` and `src/models.py:10`
- **AND** the Security Reviewer produced a finding at `src/auth.py:88`
- **WHEN** the synthesizer merges them
- **THEN** the final `bugs` list MUST contain three entries
- **AND** the Security finding at `src/auth.py:88` MUST be included

#### Scenario: Security finding overlaps with bug finding

- **GIVEN** the judge produced a bug at `src/api.py:42` (severity `major`, logic error)
- **AND** the Security Reviewer reports a vulnerability at `src/api.py:42` (severity `critical`)
- **WHEN** the synthesizer merges them
- **THEN** exactly one entry for `src/api.py:42` SHALL appear in the final list
- **AND** the severity MUST be the higher of the two (`critical` in this case)
- **AND** the description MUST reference both the bug and security aspects

---

### SYN-003 — Synthesizer attaches Cross-Repo Impact warnings

The synthesizer MUST attach the Cross-Repo Impact Reviewer's output directly to `ReviewOutput.impact_warnings`. Graph-derived `ImpactWarning` items from the enrichment step MUST also be included if they are not already covered by the reviewer's output.

**Rationale:** The `impact_warnings` field comes from two sources: graph enrichment (deterministic) and reviewer analysis (LLM). The synthesizer merges both.

#### Scenario: Impact warnings from both sources

- **GIVEN** graph enrichment produced two `ImpactWarning` items
- **AND** the Cross-Repo Impact Reviewer produced one additional grounded `ImpactWarning`
- **WHEN** the synthesizer assembles `ReviewOutput`
- **THEN** `impact_warnings` MUST contain all three items (deduplicated by `changed_file` + `affected_service`)
- **AND** no duplicate SHALL appear for the same (changed_file, affected_service) pair

#### Scenario: No impact data available

- **GIVEN** graph enrichment returned no warnings
- **AND** the Cross-Repo Impact Reviewer produced no findings
- **WHEN** the synthesizer assembles `ReviewOutput`
- **THEN** `impact_warnings` MUST be an empty list

---

### SYN-004 — Synthesizer computes final `approved` status

The synthesizer MUST set `ReviewOutput.approved = False` when any of these conditions hold:
- One or more `critical` bugs are present in the final bug list.
- The Security Reviewer reports a `critical` vulnerability.
- One or more `high` severity `ImpactWarning` items exist.

Otherwise, `approved` SHOULD be `True`.

**Rationale:** The `approved` flag is a downstream signal for merge gates. It must reflect the most severe findings across all specialists.

#### Scenario: Critical bug → not approved

- **GIVEN** the final bug list contains a `critical` bug
- **WHEN** the synthesizer computes the `approved` field
- **THEN** `approved` MUST be `False`

#### Scenario: Only minor bugs → approved

- **GIVEN** the final bug list contains only `minor` bugs
- **AND** no Security Reviewer findings exist
- **AND** no `high` severity impact warnings exist
- **WHEN** the synthesizer computes the `approved` field
- **THEN** `approved` SHOULD be `True`

#### Scenario: High-severity impact warning → not approved

- **GIVEN** the final bug list is empty
- **AND** an `ImpactWarning` with `severity: "high"` exists
- **WHEN** the synthesizer computes the `approved` field
- **THEN** `approved` MUST be `False`

---

### SYN-005 — Synthesizer produces summary

The synthesizer MUST produce a human-readable `summary` string covering:
- Number of bugs found, by severity.
- Security findings summary if any.
- Cross-repo impact summary if any.
- Overall approval recommendation.

**Rationale:** The `summary` field is the first thing a human sees. It must aggregate findings from all specialists.

#### Scenario: Summary covers all specialist outputs

- **GIVEN** bugs (2 major, 1 minor), 1 security finding (critical), and 2 impact warnings
- **WHEN** the synthesizer generates the summary
- **THEN** the summary MUST mention bug count and severities
- **AND** it MUST reference security concerns
- **AND** it MUST reference cross-repo impacts
- **AND** it MUST end with a clear approval recommendation

---

### SYN-006 — Synthesizer produces valid ReviewOutput

The synthesizer's final output MUST validate against the `ReviewOutput` Pydantic model without errors.

#### Scenario: Synthesizer output passes model validation

- **GIVEN** the synthesizer has assembled all inputs
- **WHEN** `ReviewOutput(**synthesizer_output)` is called
- **THEN** no `ValidationError` SHALL be raised
- **AND** `summary` MUST be a non-empty string
- **AND** `bugs` MUST be `list[BugReport]`
- **AND** `approved` MUST be `bool`
- **AND** `impact_warnings` MUST be `list[ImpactWarning]`
