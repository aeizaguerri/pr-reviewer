# Spec: Cross-Repo Impact Reviewer

## Summary

A Cross-Repo Impact Reviewer agent SHALL evaluate downstream impact using only the changed-path data and graph-derived `ImpactWarning` context. It MUST NOT invent impact evidence. Unsupported impact claims SHALL be discarded or downgraded. Its output feeds into the synthesizer's `impact_warnings` field.

---

## Requirements

### CRI-001 — Cross-Repo Impact Reviewer runs as a parallel specialist

The orchestrator MUST launch a Cross-Repo Impact Reviewer agent concurrently with Bug Reviewer A/B and the Security Reviewer. It MUST receive the same PR context, including any graph enrichment output.

**Rationale:** Cross-repo impact requires graph context but is a distinct concern from code-level bug or security review.

#### Scenario: Cross-Repo Impact Reviewer scheduled in parallel

- **GIVEN** the orchestrator begins specialist execution
- **WHEN** specialists are launched
- **THEN** the Cross-Repo Impact Reviewer MUST start within the same concurrent fan-out
- **AND** it MUST NOT wait for Bug Reviewers or Security Reviewer to complete

#### Scenario: Cross-Repo Impact Reviewer receives graph enrichment

- **GIVEN** graph enrichment produced `ImpactWarning` items
- **WHEN** the Cross-Repo Impact Reviewer is invoked
- **THEN** it MUST receive the formatted impact section from `_build_impact_section()` as part of its context
- **AND** it MUST also receive changed file paths extracted from the diff

---

### CRI-002 — Grounding requirement: cite evidence only

The Cross-Repo Impact Reviewer MUST only reason about impacts that are supported by available graph `ImpactWarning` evidence and changed file paths. It MUST NOT fabricate downstream dependencies or affected services that are not present in the graph output or changed-path list.

**Rationale:** Hallucinated cross-repo impact is dangerous. The reviewer must be constrained to available evidence.

#### Scenario: Impact claim backed by graph evidence is allowed

- **GIVEN** the graph enrichment produced an `ImpactWarning` saying `src/payment/events.py` affects `notification-service` in repo `notifications`
- **WHEN** the Cross-Repo Impact Reviewer evaluates this
- **THEN** it MAY include a finding that references `notification-service`
- **AND** the finding MUST cite the specific changed file and affected entity from the warning

#### Scenario: Unsupported impact claim is discarded

- **GIVEN** no graph `ImpactWarning` exists for a downstream service `analytics`
- **AND** no changed file path links logically to `analytics`
- **WHEN** the Cross-Repo Impact Reviewer proposes an impact on `analytics`
- **THEN** the output validator (or synthesizer) MUST discard or downgrade that claim
- **AND** the final `impact_warnings` list MUST NOT include the unsupported claim

#### Scenario: Grounding when graph enrichment is unavailable

- **GIVEN** the graph enrichment step failed or returned no warnings
- **WHEN** the Cross-Repo Impact Reviewer is invoked
- **THEN** it MUST NOT produce impact warnings
- **AND** its output SHALL be empty (no impact claims)

---

### CRI-003 — Cross-Repo output format

The Cross-Repo Impact Reviewer's output MUST be parseable into `list[ImpactWarning]` items, matching the existing `ImpactWarning` schema: `changed_file`, `changed_entity`, `affected_service`, `affected_repository`, `relationship_type`, `severity`, and `description`.

**Rationale:** The synthesizer attaches these directly to `ReviewOutput.impact_warnings`.

#### Scenario: Valid ImpactWarning from reviewer

- **GIVEN** the Cross-Repo Impact Reviewer produces a finding
- **WHEN** its output is parsed
- **THEN** the finding MUST validate against the `ImpactWarning` Pydantic model
- **AND** `changed_file` MUST match one of the changed paths
- **AND** `affected_service` and `affected_repository` MUST correspond to an existing graph warning or be derivable from changed paths

#### Scenario: Multiple impact warnings

- **GIVEN** the PR affects two contracts consumed by different downstream services
- **WHEN** the Cross-Repo Impact Reviewer evaluates the changes
- **THEN** it MAY produce multiple `ImpactWarning` items
- **AND** each item MUST independently satisfy the grounding requirement

---

### CRI-004 — No autonomous GitHub posting

The Cross-Repo Impact Reviewer MUST NOT have access to `post_review_comments` or any GitHub API tool.

**Rationale:** Same exactly-once invariant as all other specialists.

#### Scenario: Cross-Repo Impact Reviewer has no posting capability

- **GIVEN** the Cross-Repo Impact Reviewer agent is configured
- **WHEN** its tool list is inspected
- **THEN** it MUST NOT include `post_review_comments` or any function that writes to the GitHub API
