# Spec: Exactly-Once GitHub Posting

## Summary

GitHub review posting SHALL occur exactly once per review request and only after final synthesis. No specialist reviewer, Agno Team member, or intermediate agent SHALL have the capability to post GitHub comments. The existing `post_review_comments()` function SHALL be the single posting boundary.

---

## Requirements

### POST-001 — Posting occurs exactly once after synthesis

`post_review_comments()` MUST be called exactly once per successful review. It MUST be invoked only after the synthesizer has produced a valid `ReviewOutput`. If the final bug list is empty, posting MAY be skipped (as in the current behavior), but the posting function itself SHALL NOT be callable from any other code path.

**Rationale:** Duplicate or partial review comments on a PR create confusion. Atomic, exactly-once posting is a correctness requirement.

#### Scenario: Single invocation after synthesis

- **GIVEN** a review completes with bugs in the final synthesized `ReviewOutput`
- **WHEN** the orchestrator reaches the posting phase
- **THEN** `post_review_comments()` MUST be called exactly once
- **AND** the call MUST happen after the synthesizer returns
- **AND** no other call to `post_review_comments()` SHALL occur for the same review request

#### Scenario: No bugs → no posting

- **GIVEN** the final synthesized `ReviewOutput` has an empty `bugs` list
- **WHEN** the orchestrator reaches the posting phase
- **THEN** `post_review_comments()` MUST NOT be called
- **AND** the review MUST still return a valid `ReviewOutput`

#### Scenario: Posting skipped when flag prevents it

- **GIVEN** the existing flow mode or config disables posting (e.g., `Config.POST_REVIEW` is `False`)
- **WHEN** the orchestrator reaches the posting phase
- **THEN** `post_review_comments()` MUST NOT be called
- **AND** the review MUST still return a valid `ReviewOutput`

---

### POST-002 — No specialist can post to GitHub

No Bug Reviewer A/B agent, Security Reviewer, Cross-Repo Impact Reviewer, judge agent, or Agno Team member SHALL have `post_review_comments` or any GitHub API write function in its tool list. Specialist agents MUST be read-only with respect to GitHub.

**Rationale:** If any subagent can post, the exactly-once invariant is broken. The orchestrator is the only component trusted with side effects.

#### Scenario: Tool lists are GitHub-write-free

- **GIVEN** any specialist agent (Bug Reviewer A, Bug Reviewer B, Security Reviewer, Cross-Repo Impact Reviewer, judge)
- **WHEN** its configured tool list is inspected
- **THEN** it MUST NOT contain `post_review_comments`
- **AND** it MUST NOT contain any function that calls `httpx.post` to `api.github.com`
- **AND** it MUST NOT have access to a `github_token`

#### Scenario: Agno Team has no posting tools

- **GIVEN** the Agno Team wrapping Bug Reviewer A/B
- **WHEN** its configured tool list is inspected
- **THEN** it MUST NOT contain `post_review_comments` or any GitHub write function

---

### POST-003 — Posting uses existing post_review_comments boundary

The orchestrator MUST call the existing `post_review_comments()` function from `src/reviewer/tools.py`. The function's signature, retry logic, and 422 fallback behavior MUST remain unchanged unless a later approved change explicitly alters them.

**Rationale:** The function is already tested for retry, 422 fallback, and payload correctness. Reusing it avoids duplicating GitHub API logic.

#### Scenario: Call with bugs from synthesized output

- **GIVEN** the synthesized `ReviewOutput` contains 3 `BugReport` items
- **WHEN** `post_review_comments()` is called
- **THEN** the comments JSON MUST be built from the synthesized bug list via `_bugs_to_comments()`
- **AND** the `summary` parameter MUST be the synthesized summary
- **AND** the `commit_sha` and `pr_number` MUST match the originally fetched PR data

#### Scenario: 422 fallback still works

- **GIVEN** `post_review_comments()` receives a 422 from GitHub
- **WHEN** the fallback path executes
- **THEN** it MUST post as a top-level review comment (existing behavior)
- **AND** the orchestrator MUST NOT attempt a second inline-comment post
