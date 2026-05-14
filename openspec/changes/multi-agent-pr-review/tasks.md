# Tasks: multi-agent-pr-review

## Review Workload Forecast

| Field                   | Value                                                                                             |
| ----------------------- | ------------------------------------------------------------------------------------------------- |
| Estimated changed lines | 600–900                                                                                           |
| 400-line budget risk    | High                                                                                              |
| Chained PRs recommended | Yes                                                                                               |
| Suggested split         | PR 1 (contracts/routing) → PR 2 (agent runners + Bug Team) → PR 3 (fan-out/judge/posting/cleanup) |
| Delivery strategy       | chained-prs                                                                                       |
| Chain strategy          | feature-branch-chain                                                                              |

```text
Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High
```

---

## Phase: SDD Tasks — `multi-agent-pr-review`

**Strict TDD active.** Test runner: `uv run pytest`. Linter: `uv run ruff check .`.  
All tasks follow RED → GREEN → TRIANGULATE → REFACTOR unless marked pure-implementation.

---

## Chained PR Strategy

Use **feature-branch-chain** for this change. Create a draft/no-merge tracker branch/PR for `multi-agent-pr-review`; PR 1 targets the tracker branch, PR 2 targets PR 1's branch, and PR 3 targets PR 2's branch. Keep every PR focused, include its tests with the behavior it verifies, and retarget/rebase if a child PR shows polluted diffs.

Dependency diagram:

```text
main
└── tracker: multi-agent-pr-review (draft/no-merge)
    └── PR 1 📍 contracts/context/routing
        └── PR 2 specialist runners + Bug Team
            └── PR 3 fan-out/judge/posting/cleanup
```

## PR 1: Contracts, Context, and Routing Seam

### 1.1 [x] [RED] Add tests for multi-agent routing in `review_pr_with_config`

**File:** `src/reviewer/tests/test_multi_agent_routing.py` (new)

**What to test:**

- `review_pr_with_config()` calls the new orchestrator (mock or import); it no longer calls `_build_agent_with_config` directly.
- No mono-agent branch exists inside `review_pr_with_config()`.
- `review_pr_with_config()` still returns `ReviewOutput`.
- `_build_agent_with_config` and `_build_agent` are not called from `review_pr_with_config()`.

**Why first:** routing is the seam between public API and new internals. All downstream tasks depend on this contract.

---

### 1.2 [x] [GREEN] Create internal specialist output models

**Files:** `src/reviewer/models.py`

**What to add (internal, not exported from `__init__`):**

```python
class SpecialistBugOutput(BaseModel):
    """Output from a Bug-reviewer specialist."""
    bugs: list[BugReport] = Field(default_factory=list)
    provider: str = Field(default="")
    raw_content: str = Field(default="")

class SpecialistSecurityOutput(BaseModel):
    """Output from the Security-reviewer specialist."""
    bugs: list[BugReport] = Field(default_factory=list)
    raw_content: str = Field(default="")

class SpecialistImpactOutput(BaseModel):
    """Output from the Cross-Repo Impact reviewer."""
    impact_warnings: list[ImpactWarning] = Field(default_factory=list)
    raw_content: str = Field(default="")

class SpecialistFailure(BaseModel):
    """Marker for a specialist that failed or timed out."""
    role: str
    reason: str

class ReviewContext(BaseModel):
    """Immutable shared context built once before fan-out."""
    owner: str
    repo: str
    pr_number: int
    head_sha: str
    pr_title: str
    diff_text: str
    changed_paths: list[str]
    impact_result: ImpactResult | None = None
    shared_prompt: str = ""  # impact_section + _make_prompt()
```

**Do not modify** `BugReport`, `ReviewOutput`, `ImpactWarning`, or `ImpactResult`.

---

### 1.3 [x] [REFACTOR] Add specialist timeout config constant

**File:** `src/core/config.py`

**Add:**

```python
REVIEW_SPECIALIST_TIMEOUT_SECONDS: int = int(os.getenv("REVIEW_SPECIALIST_TIMEOUT_SECONDS", "120"))
```

No changes to existing config keys.

---

### 1.4 [x] [GREEN] Add role-specific prompt constants

**File:** `src/reviewer/prompts.py`

**Add four new lazy-load constants:**

- `BUG_REVIEWER_INSTRUCTIONS` — role: code-defect only; excludes security and cross-repo impact; references the XML-delimited diff prompt format.
- `SECURITY_REVIEWER_INSTRUCTIONS` — role: CWE-style vulnerabilities only; excludes general bugs and impact analysis.
- `CROSS_REPO_IMPACT_REVIEWER_INSTRUCTIONS` — role: cross-repo impact; may only cite changed paths and `ImpactWarning` graph evidence; outputs empty when no evidence exists.
- `JUDGE_INSTRUCTIONS` — role: compare Bug Reviewer A vs B, deduplicate by `(file, line, category)`, resolve conflicts, emit structured JSON array of deduplicated `BugReport`-shaped dicts.

**Implementation:** Use the same `__getattr__` lazy-load pattern as `REVIEWER_INSTRUCTIONS`. Each instruction set must include the XML-delimited diff prompt wrapper (`<pr_title>`, `<diff_content>`) matching the existing format.

---

### 1.5 [x] [RED] Add tests for `ReviewContext` builder

**File:** `src/reviewer/tests/test_orchestrator_context.py` (new)

**What to test:**

- `build_review_context()` (helper under `src/reviewer/orchestrator.py`) returns a `ReviewContext` with all fields populated.
- `build_review_context()` is called exactly once per `review_pr_with_config()` invocation.
- Graph enrichment is gated by `Config.ENABLE_GRAPH_ENRICHMENT`.
- `shared_prompt` includes both impact section (when available) and the XML-delimited diff wrapper.

---

### 1.6 [x] [GREEN] Implement `build_review_context()` helper

**File:** `src/reviewer/orchestrator.py` (new)

**What to implement:**

```python
def build_review_context(
    owner: str, repo: str, pr_number: int,
    head_sha: str, pr_title: str, diff_text: str,
    github_token: str = "",
) -> ReviewContext:
```

- Extract `changed_paths` using existing `_extract_changed_paths(diff_text)` from `agent.py` (import).
- Run `_enrich_with_graph(diff_text)` to get `impact_result` and `impact_section`.
- Build `shared_prompt = impact_section + _make_prompt(pr_title, diff_text)`.
- Return `ReviewContext(...)` with `shared_prompt` populated.
- Raise on `fetch_pr_data` failure (let it propagate to caller).

**Move** (or copy) `_extract_changed_paths` from `agent.py` to `orchestrator.py` utils if cleaner, but keep `fetch_pr_data` and `_make_prompt` imports from `agent.py`.

---

### 1.7 [x] [GREEN] Stub `run_multi_agent_review()` with single-fetcher pattern

**File:** `src/reviewer/orchestrator.py`

**Stub:**

```python
async def run_multi_agent_review(
    owner: str, repo: str, pr_number: int,
    provider_config: tuple[str, str, str],
    github_token: str = "",
    supports_structured_output: bool = True,
) -> ReviewOutput:
    # Step 1: fetch once
    diff_text, head_sha, pr_title = fetch_pr_data(owner, repo, pr_number, github_token=github_token)
    # Step 2: build context
    ctx = build_review_context(owner, repo, pr_number, head_sha, pr_title, diff_text, github_token)
    # Step 3: stub fan-out — raise NotImplementedError until PR 2
    raise NotImplementedError("Fan-out not yet implemented")
```

---

### 1.8 [x] [GREEN] Wire `review_pr_with_config()` to orchestrator

**File:** `src/reviewer/agent.py`

**Change `review_pr_with_config()` body to:**

```python
    return run_multi_agent_review(
        owner=owner,
        repo=repo,
        pr_number=pr_number,
        provider_config=provider_config,
        github_token=github_token,
        supports_structured_output=supports_structured_output,
    )
```

**Delete or comment out** the old mono-agent step-by-step body (steps 1–5).  
**Preserve** `_sanitize_title`, `_make_prompt`, `_extract_changed_paths`, `_enrich_with_graph`, `_bugs_to_comments`, `_log_full_llm_response`, `_parse_failure_result` — they are still used by `orchestrator.py` via imports.

**Do not delete** `_build_agent` and `_build_agent_with_config` until PR 3 (agents still need them as imports until Bug Team is implemented).

---

### 1.9 [x] [RED] Add tests for `run_multi_agent_review()` routing + response shape

**File:** `src/reviewer/tests/test_multi_agent_routing.py`

**Extend tests:**

- `run_multi_agent_review()` is called when `review_pr_with_config()` is invoked.
- Return type is `ReviewOutput` (Pydantic validation passes).
- `fetch_pr_data` is called exactly once.
- `build_review_context` is called exactly once.
- Currently asserts `NotImplementedError` (RED) until fan-out is wired in PR 2.

---

### 1.10 [x] [GREEN] Add timeout config to backend reviewer service (no-op pass-through)

**File:** `backend/core/config.py`

**Add:**

```python
REVIEW_SPECIALIST_TIMEOUT_SECONDS: int = int(os.getenv("REVIEW_SPECIALIST_TIMEOUT_SECONDS", "120"))
```

Mirror the `src/core/config.py` addition. The backend layer does not directly use it yet, but it provides parity and avoids a config gap.

**Run:** `uv run ruff check backend/core/config.py` — expect clean.

---

### 1.11 [x] [TRIANGULATE] Run full test suite — PR 1 gate

**Run:** `uv run pytest src/reviewer/tests/test_multi_agent_routing.py src/reviewer/tests/test_orchestrator_context.py -v`

**Expected:**

- Routing tests pass (orchestrator called, response shape valid).
- Context builder tests pass (all fields populated).
- Fan-out tests fail with `NotImplementedError` (expected — stub in place).

**Run lint:** `uv run ruff check src/reviewer/orchestrator.py src/reviewer/agent.py src/reviewer/prompts.py src/reviewer/models.py src/core/config.py backend/core/config.py`

**Deliverable for PR 1:** Models, prompts, context builder, routing seam, and backend config added. Fan-out and agents are stubbed.

---

## PR 2: Specialist Agent Runners and Bug Team

### 2.1 [x] [RED] Add tests for Bug Reviewer A/B identical prompt enforcement

**File:** `src/reviewer/tests/test_bug_team.py` (new)

**What to test:**

- Both Bug Reviewer A and Bug Reviewer B receive an identical prompt string (same `ReviewContext.shared_prompt`).
- Neither Bug Reviewer A nor B receives the other's raw output as input.
- Both agents are configured with the same model from `provider_config`.
- Both agents are created without `github_token` and without posting tools.

---

### 2.2 [x] [GREEN] Implement Bug Reviewer A/B as Agno Agents in a Team

**File:** `src/reviewer/orchestrator.py`

**Add imports:**

```python
from agno.agent import Agent
from agno.models.openai.like import OpenAILike
from agno.team import Team
```

**Implement:**

```python
async def _run_bug_reviewers(
    ctx: ReviewContext,
    provider_config: tuple[str, str, str],
    supports_structured_output: bool,
) -> tuple[SpecialistBugOutput, SpecialistBugOutput]:
    model_id, base_url, api_key = provider_config

    # Build the prompt that both reviewers receive
    prompt = ctx.shared_prompt

    # Each agent gets BUG_REVIEWER_INSTRUCTIONS + prompt
    # NO tools — especially no github_token or post_review_comments
    agent_a = Agent(
        id="bug-reviewer-a",
        model=OpenAILike(id=model_id, base_url=base_url, api_key=api_key),
        instructions=BUG_REVIEWER_INSTRUCTIONS,
        output_schema=SpecialistBugOutput if supports_structured_output else None,
        markdown=False,
    )
    agent_b = Agent(
        id="bug-reviewer-b",
        model=OpenAILike(id=model_id, base_url=base_url, api_key=api_key),
        instructions=BUG_REVIEWER_INSTRUCTIONS,
        output_schema=SpecialistBugOutput if supports_structured_output else None,
        markdown=False,
    )

    # Agno Team in broadcast mode — leader prompt is the shared context;
    # members receive it without seeing each other's outputs until judge phase.
    team = Team(
        id="bug-review-team",
        mode="broadcast",
        agents=[agent_a, agent_b],
        leader_prompt=(
            "You are the Bug Review Team. Broadcast the following PR context "
            "to all reviewers and wait for their independent outputs.\n\n"
            f"{prompt}"
        ),
    )

    run = team.run()
    # Extract raw content from each member's response
    outputs = []
    for msg in run.messages:
        # Filter for member responses (not leader broadcasts)
        if msg.role == "assistant" and msg.agent_id in ("bug-reviewer-a", "bug-reviewer-b"):
            raw = msg.content if isinstance(msg.content, str) else ""
            outputs.append(_parse_specialist_bug_output(raw, msg.agent_id))

    if len(outputs) < 2:
        raise RuntimeError(f"Expected 2 bug reviewer outputs, got {len(outputs)}")
    return outputs[0], outputs[1]
```

**Parse helper:**

```python
def _parse_specialist_bug_output(raw: str, role: str) -> SpecialistBugOutput:
    try:
        data = json.loads(raw)
        out = SpecialistBugOutput(**data)
    except Exception:
        _log_full_llm_response(raw, ctx.owner, ctx.repo, ctx.pr_number)
        return SpecialistBugOutput(bugs=[], provider=role, raw_content=raw)
    out.provider = role
    out.raw_content = raw
    return out
```

---

### 2.3 [x] [RED] Add tests for Security Reviewer isolation

**File:** `src/reviewer/tests/test_security_reviewer.py` (new)

**What to test:**

- Security Reviewer agent is created without `github_token` and without posting tools.
- Security Reviewer receives `SECURITY_REVIEWER_INSTRUCTIONS` + shared prompt.
- On structured-output parse failure, returns `SpecialistFailure` with `role="security-reviewer"`.
- Failure of Security Reviewer does not block other specialists.

---

### 2.4 [x] [GREEN] Implement Security Reviewer runner

**File:** `src/reviewer/orchestrator.py`

```python
async def _run_security_reviewer(
    ctx: ReviewContext,
    provider_config: tuple[str, str, str],
    supports_structured_output: bool,
    timeout: int,
) -> SpecialistSecurityOutput | SpecialistFailure:
    model_id, base_url, api_key = provider_config
    agent = Agent(
        id="security-reviewer",
        model=OpenAILike(id=model_id, base_url=base_url, api_key=api_key),
        instructions=SECURITY_REVIEWER_INSTRUCTIONS,
        output_schema=SpecialistSecurityOutput if supports_structured_output else None,
        markdown=False,
    )
    try:
        run = asyncio.wait_for(agent.run_async(ctx.shared_prompt), timeout=timeout)
        raw = run.content if isinstance(run.content, str) else ""
        return _parse_specialist_security_output(raw)
    except asyncio.TimeoutError:
        logger.warning("Security reviewer timed out after %ds", timeout)
        return SpecialistFailure(role="security-reviewer", reason="timeout")
    except Exception as exc:
        logger.warning("Security reviewer failed: %s", exc)
        return SpecialistFailure(role="security-reviewer", reason=str(exc))
```

**Parse helper:**

```python
def _parse_specialist_security_output(raw: str) -> SpecialistSecurityOutput:
    try:
        data = json.loads(raw)
        return SpecialistSecurityOutput(**data, raw_content=raw)
    except Exception:
        _log_full_llm_response(raw, ctx.owner, ctx.repo, ctx.pr_number)
        return SpecialistSecurityOutput(bugs=[], raw_content=raw)
```

---

### 2.5 [x] [RED] Add tests for Cross-Repo Impact Reviewer grounding

**File:** `src/reviewer/tests/test_cross_repo_reviewer.py` (new)

**What to test:**

- Cross-Repo Impact Reviewer receives shared prompt that includes impact section (when `Config.ENABLE_GRAPH_ENRICHMENT` and `impact_result.warnings` exist).
- When `impact_result.warnings` is empty, Cross-Repo Impact Reviewer output is empty.
- Cross-Repo Impact Reviewer is created without `github_token` and without posting tools.
- On structured-output parse failure, returns `SpecialistFailure`.

---

### 2.6 [x] [GREEN] Implement Cross-Repo Impact Reviewer runner

**File:** `src/reviewer/orchestrator.py`

```python
async def _run_cross_repo_reviewer(
    ctx: ReviewContext,
    provider_config: tuple[str, str, str],
    supports_structured_output: bool,
    timeout: int,
) -> SpecialistImpactOutput | SpecialistFailure:
    # Short-circuit if no graph evidence
    if not ctx.impact_result or not ctx.impact_result.warnings:
        return SpecialistImpactOutput(impact_warnings=[], raw_content="")

    model_id, base_url, api_key = provider_config
    agent = Agent(
        id="cross-repo-impact-reviewer",
        model=OpenAILike(id=model_id, base_url=base_url, api_key=api_key),
        instructions=CROSS_REPO_IMPACT_REVIEWER_INSTRUCTIONS,
        output_schema=SpecialistImpactOutput if supports_structured_output else None,
        markdown=False,
    )
    try:
        run = asyncio.wait_for(agent.run_async(ctx.shared_prompt), timeout=timeout)
        raw = run.content if isinstance(run.content, str) else ""
        return _parse_specialist_impact_output(raw)
    except asyncio.TimeoutError:
        logger.warning("Cross-repo impact reviewer timed out after %ds", timeout)
        return SpecialistFailure(role="cross-repo-impact-reviewer", reason="timeout")
    except Exception as exc:
        logger.warning("Cross-repo impact reviewer failed: %s", exc)
        return SpecialistFailure(role="cross-repo-impact-reviewer", reason=str(exc))
```

**Parse helper:**

```python
def _parse_specialist_impact_output(raw: str) -> SpecialistImpactOutput:
    try:
        data = json.loads(raw)
        return SpecialistImpactOutput(**data, raw_content=raw)
    except Exception:
        _log_full_llm_response(raw, ctx.owner, ctx.repo, ctx.pr_number)
        return SpecialistImpactOutput(impact_warnings=[], raw_content=raw)
```

---

### 2.7 [x] [TRIANGULATE] Run PR 2 tests

**Run:** `uv run pytest src/reviewer/tests/test_bug_team.py src/reviewer/tests/test_security_reviewer.py src/reviewer/tests/test_cross_repo_reviewer.py -v`

**Run lint:** `uv run ruff check src/reviewer/orchestrator.py`

**Deliverable for PR 2:** All three specialist runners implemented and individually tested. Fan-out wiring (step 3 in `run_multi_agent_review`) still a stub.

---

## PR 3: Fan-Out, Judge/Deduper/Synthesizer, Exactly-Once Posting, and Cleanup

### 3.1 [x] [RED] Add tests for parallel fan-out orchestration

**File:** `src/reviewer/tests/test_fan_out.py` (new)

**What to test:**

- All three specialist runners are scheduled concurrently via `asyncio.gather`.
- One specialist failure does not cancel other specialists.
- Timeout per specialist is respected.
- Results are aggregated into a dict keyed by role.
- `asyncio.gather(..., return_exceptions=True)` is used so one failure is non-fatal.

---

### 3.2 [x] [RED] Add tests for Judge/Deduper

**File:** `src/reviewer/tests/test_judge.py` (new)

**What to test:**

- `_run_judge()` receives Bug A and Bug B `SpecialistBugOutput` objects.
- Duplicate bugs (same `file`, `line`, `severity`) collapse to one.
- Different-severity duplicates escalate to the higher severity.
- Non-deterministic (random) dedupe is deterministic by sort key.
- `_run_judge()` returns `list[dict]` matching `BugReport` field keys.
- Judge fatal failure returns an empty bug list (not an exception).

---

### 3.3 [x] [RED] Add tests for Synthesizer → `ReviewOutput`

**File:** `src/reviewer/tests/test_synthesizer.py` (new)

**What to test:**

- Synthesizer merges: judged bugs (A/B deduped) + security bugs.
- No duplicates across judged and security bug lists (same dedupe key).
- `approved` is `False` when any bug has `severity == "critical"` or when any `impact_warning` has `severity == "high"`.
- `approved` is `True` otherwise and bug list is empty.
- `summary` is a non-empty string.
- Output validates against `ReviewOutput` Pydantic model.
- When all specialists fail, synthesizer falls back to `_parse_failure_result`.

---

### 3.4 [x] [RED] Add tests for exactly-once posting invariant

**File:** `src/reviewer/tests/test_posting_invariant.py` (new)

**What to test:**

- `post_review_comments` is called exactly once per successful `run_multi_agent_review()` with bugs.
- `post_review_comments` is called zero times when `result.bugs` is empty.
- `post_review_comments` is called zero times when synthesizer returns `_parse_failure_result`.
- No specialist runner (Bug A/B, Security, Cross-Repo) has access to `post_review_comments` or `github_token`.
- `_bugs_to_comments()` produces correct payload shape.

---

### 3.5 [x] [GREEN] Implement `_run_judge()`

**File:** `src/reviewer/orchestrator.py`

```python
def _run_judge(
    output_a: SpecialistBugOutput,
    output_b: SpecialistBugOutput,
    ctx: ReviewContext,
) -> list[dict]:
    """Deduplicate Bug A and B outputs, return list of BugReport-shaped dicts."""
    all_bugs: list[SpecialistBugOutput] = [output_a, output_b]

    bug_records: list[dict] = []
    for specialist in all_bugs:
        for bug in specialist.bugs:
            bug_records.append(bug.model_dump(mode="json"))

    # Deterministic dedupe key: (file, line, severity, description[:50].lower())
    seen: dict[str, dict] = {}
    for record in bug_records:
        key = (
            record["file"],
            record["line"],
            record["severity"],
            record["description"][:50].lower(),
        )
        if key not in seen:
            seen[key] = record
        else:
            # Escalate severity on conflict
            severity_order = {"minor": 0, "major": 1, "critical": 2}
            existing = seen[key]
            if severity_order.get(record["severity"], 0) > severity_order.get(existing["severity"], 0):
                seen[key] = record

    return list(seen.values())
```

**Add `import json`** if not already present.

---

### 3.6 [x] [GREEN] Implement synthesizer helper

**File:** `src/reviewer/orchestrator.py`

```python
def _synthesize(
    judged_bugs: list[dict],
    security_bugs: list[BugReport],
    impact_warnings: list[ImpactWarning],
    ctx: ReviewContext,
) -> ReviewOutput:
    """Merge all specialist outputs into a single ReviewOutput."""

    # Combine judged + security bugs, dedupe by key
    all_bugs: list[BugReport] = []
    seen_keys: set[str] = set()
    for bug_dict in judged_bugs:
        key = f"{bug_dict['file']}:{bug_dict['line']}:{bug_dict['severity']}"
        if key not in seen_keys:
            seen_keys.add(key)
            all_bugs.append(BugReport(**bug_dict))

    for bug in security_bugs:
        key = f"{bug.file}:{bug.line}:{bug.severity}"
        if key not in seen_keys:
            seen_keys.add(key)
            all_bugs.append(bug)

    # Determine approval
    has_critical = any(b.severity == "critical" for b in all_bugs)
    has_high_impact = any(w.severity == "high" for w in impact_warnings)
    approved = not has_critical and not has_high_impact and len(all_bugs) == 0

    # Build summary
    if all_bugs:
        summaries = []
        for severity in ["critical", "major", "minor"]:
            count = sum(1 for b in all_bugs if b.severity == severity)
            if count:
                summaries.append(f"{count} {severity} bug(s)")
        summary = f"PR review complete. Found {', '.join(summaries)}."
    else:
        summary = "No bugs detected."

    return ReviewOutput(
        summary=summary,
        bugs=all_bugs,
        approved=approved,
        impact_warnings=impact_warnings,
    )
```

---

### 3.7 [x] [GREEN] Implement parallel fan-out and complete `run_multi_agent_review()`

**File:** `src/reviewer/orchestrator.py`

Replace the stub in `run_multi_agent_review()` with:

```python
async def run_multi_agent_review(
    owner: str, repo: str, pr_number: int,
    provider_config: tuple[str, str, str],
    github_token: str = "",
    supports_structured_output: bool = True,
) -> ReviewOutput:
    # Step 1: fetch once
    diff_text, head_sha, pr_title = fetch_pr_data(owner, repo, pr_number, github_token=github_token)

    # Step 2: build context
    ctx = build_review_context(owner, repo, pr_number, head_sha, pr_title, diff_text, github_token)

    # Step 3: fan out specialists concurrently
    timeout = Config.REVIEW_SPECIALIST_TIMEOUT_SECONDS

    # Bug Team runs as Agno Team (blind A/B)
    bug_a, bug_b = await _run_bug_reviewers(ctx, provider_config, supports_structured_output)

    # Specialist runners run in parallel with bug reviewers
    security_result, cross_repo_result = await asyncio.gather(
        _run_security_reviewer(ctx, provider_config, supports_structured_output, timeout),
        _run_cross_repo_reviewer(ctx, provider_config, supports_structured_output, timeout),
        return_exceptions=True,
    )

    # Normalize specialist results
    security_bugs: list[BugReport] = []
    if isinstance(security_result, SpecialistFailure):
        logger.warning("Security reviewer failed: %s", security_result.reason)
    else:
        security_bugs = security_result.bugs

    impact_warnings: list[ImpactWarning] = []
    if isinstance(cross_repo_result, SpecialistFailure):
        logger.warning("Cross-repo impact reviewer failed: %s", cross_repo_result.reason)
    else:
        impact_warnings = cross_repo_result.impact_warnings

    # Append graph-derived warnings if graph enrichment was active
    if ctx.impact_result and ctx.impact_result.warnings:
        for w in ctx.impact_result.warnings:
            if w not in impact_warnings:
                impact_warnings.append(w)

    # Step 4: judge/deduper
    judged_bugs: list[dict] = _run_judge(bug_a, bug_b, ctx)

    # Step 5: synthesizer
    result = _synthesize(judged_bugs, security_bugs, impact_warnings, ctx)

    # Step 6: exactly-once posting
    if result.bugs:
        comments = json.dumps(_bugs_to_comments(result.bugs))
        gh_result = post_review_comments(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            commit_sha=head_sha,
            comments=comments,
            summary=result.summary,
            github_token=github_token,
        )
        logger.info("GitHub review post result: %s", gh_result)

    return result
```

---

### 3.8 [x] [RED] Add tests for `review_pr_with_config()` + backend `ReviewResponse` compatibility

**File:** `src/reviewer/tests/test_backend_compatibility.py` (new)

**What to test:**

- End-to-end mock: `run_multi_agent_review()` returns a `ReviewOutput` that validates against the Pydantic model.
- Backend `run_review()` maps all fields correctly to `ReviewResponse`.
- `BugReportResponse` fields match `BugReport`.
- `ImpactWarningResponse` fields match `ImpactWarning`.

---

### 3.9 [x] [REFACTOR] Clean up superseded mono-agent helpers from `agent.py`

**File:** `src/reviewer/agent.py`

**After verifying all downstream tasks pass, remove or mark deprecated:**

- `_build_agent` and `_build_agent_with_config` (no longer called from `review_pr_with_config`).
- Remove unused `import html` if no other function uses it.
- Remove `REVIEWER_INSTRUCTIONS` import if unused.
- Keep `_sanitize_title`, `_make_prompt`, `_extract_changed_paths`, `_enrich_with_graph`, `_bugs_to_comments`, `_log_full_llm_response`, `_parse_failure_result` — they are imported by `orchestrator.py`.

**If any helper is still imported by tests**, preserve it and add a deprecation comment.

---

### 3.10 [x] [REFACTOR] Update/replace mono-agent tests in `test_agent.py`

**File:** `src/reviewer/tests/test_agent.py`

**Review and update:**

- Tests for `_build_agent` and `_build_agent_with_config` behavior are now testing dead code — move to `test_legacy_helpers.py` or mark with `@pytest.mark.skip(reason="superseded by multi-agent")`.
- Tests for `_sanitize_title`, `_make_prompt`, `_log_full_llm_response` remain unchanged — these helpers are still used.
- Tests for `review_pr()` and `review_pr_with_config()` now route through orchestrator — update mocks accordingly.
- Add a test that `review_pr()` also routes through `run_multi_agent_review()` (or confirm it has its own path).

---

### 3.11 [x] [TRIANGULATE] Run full test suite — PR 3 gate

**Run:** `uv run pytest -v`

**Expected:** All tests pass including new multi-agent tests.

**Run lint:** `uv run ruff check src/reviewer/ backend/`

**Run format:** `uv run ruff format src/reviewer/ backend/`

---

### 3.12 [VERIFY] Final integration check

**Verify:**

- `uv run pytest` — 100% pass (or account for known skips).
- `uv run ruff check .` — clean.
- No specialist agent has `github_token` or `post_review_comments` injected.
- `post_review_comments` appears only in `orchestrator.py` call site.
- `ReviewOutput` Pydantic validation passes end-to-end.
- `ReviewResponse` from `backend/services/reviewer.py` has all fields populated.

---

## Task Summary Table

| #    | Task                                | File(s)                                        | Type     | PR  |
| ---- | ----------------------------------- | ---------------------------------------------- | -------- | --- |
| 1.1  | Routing tests RED                   | `tests/test_multi_agent_routing.py`            | test     | 1   |
| 1.2  | Internal specialist models          | `src/reviewer/models.py`                       | impl     | 1   |
| 1.3  | Timeout config                      | `src/core/config.py`, `backend/core/config.py` | impl     | 1   |
| 1.4  | Role-specific prompts               | `src/reviewer/prompts.py`                      | impl     | 1   |
| 1.5  | Context builder tests RED           | `tests/test_orchestrator_context.py`           | test     | 1   |
| 1.6  | `build_review_context()`            | `src/reviewer/orchestrator.py`                 | impl     | 1   |
| 1.7  | Stub `run_multi_agent_review()`     | `src/reviewer/orchestrator.py`                 | impl     | 1   |
| 1.8  | Wire `review_pr_with_config()`      | `src/reviewer/agent.py`                        | impl     | 1   |
| 1.9  | Routing + response shape tests      | `tests/test_multi_agent_routing.py`            | test     | 1   |
| 1.10 | Backend timeout config              | `backend/core/config.py`                       | impl     | 1   |
| 1.11 | PR 1 gate                           | —                                              | verify   | 1   |
| 2.1  | Bug Team tests RED                  | `tests/test_bug_team.py`                       | test     | 2   |
| 2.2  | `_run_bug_reviewers()`              | `src/reviewer/orchestrator.py`                 | impl     | 2   |
| 2.3  | Security reviewer tests RED         | `tests/test_security_reviewer.py`              | test     | 2   |
| 2.4  | `_run_security_reviewer()`          | `src/reviewer/orchestrator.py`                 | impl     | 2   |
| 2.5  | Cross-repo reviewer tests RED       | `tests/test_cross_repo_reviewer.py`            | test     | 2   |
| 2.6  | `_run_cross_repo_reviewer()`        | `src/reviewer/orchestrator.py`                 | impl     | 2   |
| 2.7  | PR 2 gate                           | —                                              | verify   | 2   |
| 3.1  | Fan-out tests RED                   | `tests/test_fan_out.py`                        | test     | 3   |
| 3.2  | Judge tests RED                     | `tests/test_judge.py`                          | test     | 3   |
| 3.3  | Synthesizer tests RED               | `tests/test_synthesizer.py`                    | test     | 3   |
| 3.4  | Posting invariant tests RED         | `tests/test_posting_invariant.py`              | test     | 3   |
| 3.5  | `_run_judge()`                      | `src/reviewer/orchestrator.py`                 | impl     | 3   |
| 3.6  | `_synthesize()`                     | `src/reviewer/orchestrator.py`                 | impl     | 3   |
| 3.7  | Complete `run_multi_agent_review()` | `src/reviewer/orchestrator.py`                 | impl     | 3   |
| 3.8  | Backend compatibility tests         | `tests/test_backend_compatibility.py`          | test     | 3   |
| 3.9  | Clean up `agent.py`                 | `src/reviewer/agent.py`                        | refactor | 3   |
| 3.10 | Update mono-agent tests             | `tests/test_agent.py`                          | refactor | 3   |
| 3.11 | PR 3 gate                           | —                                              | verify   | 3   |
| 3.12 | Final integration check             | —                                              | verify   | 3   |

---

## Risks and Open Questions

| Risk                                                       | Mitigation                                                                            | Owner       |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------- | ----------- |
| Agno Team broadcast semantics not as documented            | Test with live mock run in PR 2 before wiring judge                                   | Implementer |
| Structured output schema mismatch in `SpecialistBugOutput` | Validate schema matches `BugReport` field names exactly                               | Implementer |
| `asyncio.run_async` vs `run` API changes in agno           | Pin agno version; add integration smoke test                                          | Implementer |
| Cross-repo reviewer hallucination                          | Grounding rule: short-circuit when `impact_result.warnings` empty                     | Implementer |
| Judge dedupe false positives on similar-but-different bugs | Use full `description` (not first 50 chars) for key; escalate severity on any overlap | Implementer |
| `agent.py` helper removal breaks existing test fixtures    | Review test_agent.py in PR 3 before deletion                                          | Implementer |
| PR chain merge conflicts                                   | Use stacked PRs from `multi-agent-pr-review` base; rebase sequentially                | CI/Reviewer |

---

## Criteria for Each PR Gate

**PR 1 passes gate when:**

- `uv run pytest src/reviewer/tests/test_multi_agent_routing.py src/reviewer/tests/test_orchestrator_context.py -v` passes.
- Fan-out tests fail with `NotImplementedError` (expected stub).
- `uv run ruff check src/reviewer/agent.py src/reviewer/orchestrator.py src/reviewer/prompts.py src/reviewer/models.py` is clean.

**PR 2 passes gate when:**

- All three specialist runner test files pass.
- `_run_bug_reviewers()` returns two `SpecialistBugOutput` objects.
- `asyncio.gather` scheduling test passes.

**PR 3 passes gate when:**

- `uv run pytest -v` passes (all 225+ tests).
- `uv run ruff check src/reviewer/ backend/` is clean.
- `post_review_comments` appears only in `orchestrator.py`.
- No specialist agent builder receives `github_token` or `post_review_comments`.
- `ReviewOutput` validates end-to-end.
