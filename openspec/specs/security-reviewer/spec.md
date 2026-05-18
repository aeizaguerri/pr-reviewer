# Spec: Security Reviewer

## Summary

A dedicated Security Reviewer agent SHALL run in parallel with the bug-review path. It MUST identify security-relevant findings from the PR diff and MUST NOT overlap with general bug detection or cross-repo impact assessment.

---

## Requirements

### SEC-001 — Security Reviewer runs as a parallel specialist

The orchestrator MUST launch a Security Reviewer agent concurrently with Bug Reviewer A/B and the Cross-Repo Impact Reviewer. The Security Reviewer MUST receive the same PR context as other specialists.

**Rationale:** Security review is a distinct concern that benefits from a focused, role-specific prompt and runs in parallel to avoid adding latency.

#### Scenario: Security Reviewer scheduled in parallel fan-out

- **GIVEN** the orchestrator begins specialist execution
- **WHEN** Bug Reviewer A/B, Security Reviewer, and Cross-Repo Impact Reviewer are scheduled
- **THEN** the Security Reviewer MUST start within the same concurrent fan-out
- **AND** it MUST NOT wait for Bug Reviewers to complete before starting

#### Scenario: Security Reviewer receives full PR context

- **GIVEN** PR data and graph enrichment have been prepared
- **WHEN** the Security Reviewer is invoked
- **THEN** it MUST receive the identical enriched prompt context as Bug Reviewers
- **AND** no security-relevant context SHALL be withheld

---

### SEC-002 — Security-focused prompt scope

The Security Reviewer's prompt MUST instruct it to identify vulnerabilities and security weaknesses only. It MUST NOT be instructed to find general logic bugs, style issues, or cross-repo impact.

**Rationale:** Clear scope boundaries prevent duplicate findings and keep each specialist's output focused.

#### Scenario: Security prompt is role-specific

- **GIVEN** the Security Reviewer prompt is constructed
- **WHEN** it is inspected
- **THEN** it MUST include instructions covering: injection vulnerabilities, authentication/authorization flaws, sensitive data exposure, insecure dependencies or configurations, and input validation gaps
- **AND** it MUST explicitly exclude general logic bugs
- **AND** it MUST explicitly exclude cross-repo impact reasoning

#### Scenario: Security prompt does not overlap with Bug Reviewer

- **GIVEN** both the Bug Reviewer prompt and the Security Reviewer prompt
- **WHEN** they are compared
- **THEN** the Security Reviewer's scope MUST cover vulnerabilities (CWE-aligned)
- **AND** the Bug Reviewer's scope MUST cover code defects (logic, null, off-by-one, etc.)
- **AND** there MUST be no instruction in either prompt that directs the agent to perform the other specialist's role

---

### SEC-003 — Security findings use BugReport model

The Security Reviewer's output MUST be parseable into `list[BugReport]` items. Security findings SHALL be distinguishable from general bugs in the final synthesized output through severity or description, but MUST use the same `BugReport` schema.

**Rationale:** Preserves the existing `ReviewOutput` contract. Security findings are a subset of review findings; a separate schema is unnecessary for this iteration.

#### Scenario: Security finding as BugReport

- **GIVEN** the Security Reviewer identifies an XSS vulnerability
- **WHEN** its output is parsed
- **THEN** the finding MUST be representable as a `BugReport` with:
  - `file`: the affected file path
  - `line`: the affected line number
  - `severity`: at least `major` (security findings default to `critical` or `major`)
  - `description`: a clear statement of the vulnerability
  - `suggestion`: a remediation recommendation

#### Scenario: Security findings flow into synthesis

- **GIVEN** the Security Reviewer has produced findings
- **WHEN** the synthesizer assembles the final `ReviewOutput`
- **THEN** security findings MUST appear in the `bugs` list
- **AND** security-related `approved` evaluations (e.g., critical vulnerability → `approved=False`) MUST be honored by the synthesizer

---

### SEC-004 — No autonomous GitHub posting

The Security Reviewer MUST NOT have access to `post_review_comments` or any GitHub API tool. It MUST only produce structured output for the orchestrator.

**Rationale:** Exactly-once posting is an invariant. All specialists are read-only with respect to GitHub.

#### Scenario: Security Reviewer has no posting capability

- **GIVEN** the Security Reviewer agent is configured
- **WHEN** its tool list is inspected
- **THEN** it MUST NOT include `post_review_comments` or any function that writes to the GitHub API
- **AND** it MUST NOT have access to a GitHub token
