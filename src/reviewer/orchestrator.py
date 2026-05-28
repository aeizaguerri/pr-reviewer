"""Multi-agent orchestrator for PR review.

Replaces the mono-agent flow with a hybrid orchestrator that coordinates
specialist reviewers (Bug A/B, Security, Cross-Repo Impact) and synthesises
a single ReviewOutput.
"""

import asyncio
import inspect
import json
import logging
import re
from typing import Any

from agno.agent import Agent
from agno.models.openai.like import OpenAILike

from src.core.config import Config
from src.reviewer.agent import (
    _bugs_to_comments,
    _enrich_with_graph,
    _extract_changed_paths,
    _log_full_llm_response,
    _make_prompt,
    _parse_failure_result,
)
from src.reviewer.models import (
    BugReport,
    ReviewContext,
    ReviewHealth,
    ReviewOutput,
    SpecialistBugOutput,
    SpecialistBugPayload,
    SpecialistFailure,
    SpecialistImpactPayload,
    SpecialistImpactOutput,
    SpecialistSecurityPayload,
    SpecialistSecurityOutput,
)
from src.reviewer.prompts import (
    BUG_REVIEWER_INSTRUCTIONS,
    CROSS_REPO_IMPACT_REVIEWER_INSTRUCTIONS,
    SECURITY_REVIEWER_INSTRUCTIONS,
)
from src.reviewer.tools import fetch_pr_data, post_review_comments

logger = logging.getLogger(__name__)


async def _maybe_await(value: Any) -> Any:
    """Await value when it is awaitable; otherwise return it as-is.

    Tests often use ``MagicMock`` sync return values, while real Agno calls may
    expose async APIs. This keeps runners compatible with both.
    """
    if inspect.isawaitable(value):
        return await value
    return value


def _run_coro_sync(coro):
    """Run an async orchestrator coroutine from the current sync API boundary."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(
        "run_multi_agent_review() called from an active event loop; use arun_multi_agent_review()"
    )


def build_review_context(
    owner: str,
    repo: str,
    pr_number: int,
    head_sha: str,
    pr_title: str,
    diff_text: str,
    github_token: str = "",
) -> ReviewContext:
    """Build an immutable ReviewContext from fetched PR data."""
    changed_paths = _extract_changed_paths(diff_text)
    impact_section, impact_result = _enrich_with_graph(diff_text)
    shared_prompt = impact_section + _make_prompt(pr_title, diff_text)

    return ReviewContext(
        owner=owner,
        repo=repo,
        pr_number=pr_number,
        head_sha=head_sha,
        pr_title=pr_title,
        diff_text=diff_text,
        changed_paths=changed_paths,
        impact_result=impact_result,
        shared_prompt=shared_prompt,
    )


def _safe_context_summary(
    diff_text: str,
    shared_prompt: str,
    changed_paths: list[str],
) -> dict[str, Any]:
    """Return safe diagnostics for context delivery.

    Exposes lengths, counts, and a bounded path sample.  Never includes
    full diff bodies or secret-bearing raw content.
    """
    return {
        "diff_text_length": len(diff_text),
        "shared_prompt_length": len(shared_prompt),
        "changed_paths_count": len(changed_paths),
        "changed_paths_sample": changed_paths[:5],
    }


def _build_agent(
    *,
    agent_id: str,
    instructions: str,
    provider_config: tuple[str, str, str],
    output_schema: type | None,
) -> Agent:
    """Build a read-only specialist agent with no tools or GitHub access."""
    model_id, base_url, api_key = provider_config
    return Agent(
        id=agent_id,
        model=OpenAILike(id=model_id, base_url=base_url, api_key=api_key),
        instructions=instructions,
        output_schema=output_schema,
        markdown=False,
    )


def _content_to_raw(content: Any) -> str:
    if isinstance(content, str):
        return content
    if hasattr(content, "model_dump"):
        return json.dumps(content.model_dump())
    return json.dumps(content)


def _extract_json_object_text(raw: str) -> str:
    """Return the best JSON object text found in *raw*.

    Tries direct JSON first, then fenced markdown blocks, then a balanced
    brace scan. Raises ``ValueError`` when nothing looks like a JSON object.
    """
    # 1. Direct parse — succeeds for clean JSON
    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError:
        pass

    # 2. Markdown fence extraction (try every fence, skip invalid)
    fence_matches = re.findall(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
    for candidate in fence_matches:
        candidate = candidate.strip()
        if candidate:
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

    # 3. Balanced first-object scan (string-aware)
    start = raw.find("{")
    if start == -1:
        raise ValueError("No JSON object found in response")
    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(raw[start:], start=start):
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
                continue
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = raw[start : i + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    break
                break
    raise ValueError("No valid JSON object found in response")


def _parse_specialist_payload_json(raw: str) -> dict[str, Any]:
    """Extract and parse a JSON object from *raw*, returning a dict.

    Raises on failure so existing catch blocks handle degradation.
    """
    text = _extract_json_object_text(raw)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Specialist output must be a JSON object")
    return data


def _safe_output_preview(raw: str, max_length: int = 200) -> str:
    """Return a whitespace-normalized, bounded preview of raw output."""
    preview = " ".join(raw.split())
    if len(preview) > max_length:
        preview = preview[:max_length] + "..."
    return preview


def _log_specialist_output(
    role: str,
    raw: str,
    payload: dict[str, Any] | None = None,
    parse_failed: bool = False,
    bug_count: int | None = None,
    impact_count: int | None = None,
) -> None:
    """Log safe specialist output diagnostics at INFO level."""
    extra: dict[str, Any] = {
        "role": role,
        "raw_length": len(raw),
        "preview": _safe_output_preview(raw),
        "parse_failed": parse_failed,
    }
    if payload is not None:
        extra["top_level_keys"] = list(payload.keys())
    if bug_count is not None:
        extra["bug_count"] = bug_count
    if impact_count is not None:
        extra["impact_count"] = impact_count
    logger.info("Specialist output: %s", extra)


def _specialist_payload_dict(raw: str) -> dict[str, Any]:
    data = _parse_specialist_payload_json(raw)
    cleaned = dict(data)
    for key in ("provider", "raw_content", "parse_failed"):
        cleaned.pop(key, None)
    return cleaned


def _parse_specialist_bug_output(raw: str, role: str, ctx: ReviewContext) -> SpecialistBugOutput:
    payload_dict: dict[str, Any] | None = None
    try:
        payload_dict = _parse_specialist_payload_json(raw)
        cleaned = dict(payload_dict)
        for key in ("provider", "raw_content", "parse_failed"):
            cleaned.pop(key, None)
        payload = SpecialistBugPayload(**cleaned)
        out = SpecialistBugOutput(bugs=payload.bugs)
    except Exception:
        _log_full_llm_response(raw, ctx.owner, ctx.repo, ctx.pr_number)
        _log_specialist_output(role=role, raw=raw, payload=payload_dict, parse_failed=True)
        return SpecialistBugOutput(bugs=[], provider=role, raw_content=raw, parse_failed=True)
    _log_specialist_output(
        role=role,
        raw=raw,
        payload=payload_dict,
        parse_failed=False,
        bug_count=len(out.bugs),
    )
    out.provider = role
    out.raw_content = raw
    return out


def _parse_specialist_security_output(
    raw: str, ctx: ReviewContext
) -> SpecialistSecurityOutput | SpecialistFailure:
    payload_dict: dict[str, Any] | None = None
    try:
        payload_dict = _parse_specialist_payload_json(raw)
        cleaned = dict(payload_dict)
        for key in ("provider", "raw_content", "parse_failed"):
            cleaned.pop(key, None)
        payload = SpecialistSecurityPayload(**cleaned)
        out = SpecialistSecurityOutput(bugs=payload.bugs, raw_content=raw)
    except Exception as exc:
        _log_full_llm_response(raw, ctx.owner, ctx.repo, ctx.pr_number)
        _log_specialist_output(
            role="security-reviewer", raw=raw, payload=payload_dict, parse_failed=True
        )
        return SpecialistFailure(role="security-reviewer", reason=f"parse failure: {exc}")
    _log_specialist_output(
        role="security-reviewer",
        raw=raw,
        payload=payload_dict,
        parse_failed=False,
        bug_count=len(out.bugs),
    )
    return out


def _parse_specialist_impact_output(
    raw: str, ctx: ReviewContext
) -> SpecialistImpactOutput | SpecialistFailure:
    payload_dict: dict[str, Any] | None = None
    try:
        payload_dict = _parse_specialist_payload_json(raw)
        cleaned = dict(payload_dict)
        for key in ("provider", "raw_content", "parse_failed"):
            cleaned.pop(key, None)
        payload = SpecialistImpactPayload(**cleaned)
        out = SpecialistImpactOutput(impact_warnings=payload.impact_warnings, raw_content=raw)
    except Exception as exc:
        _log_full_llm_response(raw, ctx.owner, ctx.repo, ctx.pr_number)
        _log_specialist_output(
            role="cross-repo-impact-reviewer",
            raw=raw,
            payload=payload_dict,
            parse_failed=True,
        )
        return SpecialistFailure(role="cross-repo-impact-reviewer", reason=f"parse failure: {exc}")
    _log_specialist_output(
        role="cross-repo-impact-reviewer",
        raw=raw,
        payload=payload_dict,
        parse_failed=False,
        impact_count=len(out.impact_warnings),
    )
    return out


async def _run_bug_pass(
    agent_id: str,
    ctx: ReviewContext,
    agent: Agent,
    timeout: int,
) -> SpecialistBugOutput:
    """Run a single bug reviewer pass with timeout and exception handling."""
    try:
        run = await asyncio.wait_for(_maybe_await(agent.arun(ctx.shared_prompt)), timeout=timeout)
        return _parse_specialist_bug_output(_content_to_raw(run.content), agent_id, ctx)
    except asyncio.TimeoutError:
        logger.warning("Bug reviewer %s timed out after %ds", agent_id, timeout)
        return SpecialistBugOutput(bugs=[], provider=agent_id, raw_content="", parse_failed=True)
    except Exception as exc:
        logger.warning("Bug reviewer %s failed: %s", agent_id, exc)
        return SpecialistBugOutput(bugs=[], provider=agent_id, raw_content="", parse_failed=True)


async def _run_bug_reviewers(
    ctx: ReviewContext,
    role_configs: dict[str, tuple[str, str, str]],
    supports_structured_output: bool,
) -> tuple[SpecialistBugOutput, SpecialistBugOutput]:
    """Run blind Bug Reviewer A/B using direct async agent calls."""
    schema = SpecialistBugPayload if supports_structured_output else None
    bug_config = role_configs["bug"]
    agent_a = _build_agent(
        agent_id="bug-reviewer-a",
        instructions=BUG_REVIEWER_INSTRUCTIONS,
        provider_config=bug_config,
        output_schema=schema,
    )
    agent_b = _build_agent(
        agent_id="bug-reviewer-b",
        instructions=BUG_REVIEWER_INSTRUCTIONS,
        provider_config=bug_config,
        output_schema=schema,
    )

    timeout = Config.REVIEW_SPECIALIST_TIMEOUT_SECONDS
    results = await asyncio.gather(
        _run_bug_pass("bug-reviewer-a", ctx, agent_a, timeout=timeout),
        _run_bug_pass("bug-reviewer-b", ctx, agent_b, timeout=timeout),
        return_exceptions=True,
    )

    outputs: dict[str, SpecialistBugOutput] = {}
    for agent_id, result in zip(("bug-reviewer-a", "bug-reviewer-b"), results):
        if isinstance(result, BaseException):
            logger.warning("Bug reviewer %s raised exception: %s", agent_id, result)
            outputs[agent_id] = SpecialistBugOutput(bugs=[], provider=agent_id, raw_content="", parse_failed=True)
        else:
            outputs[agent_id] = result

    return outputs["bug-reviewer-a"], outputs["bug-reviewer-b"]


async def _run_security_reviewer(
    ctx: ReviewContext,
    role_configs: dict[str, tuple[str, str, str]],
    supports_structured_output: bool,
    timeout: int,
) -> SpecialistSecurityOutput | SpecialistFailure:
    """Run the isolated security specialist."""
    agent = _build_agent(
        agent_id="security-reviewer",
        instructions=SECURITY_REVIEWER_INSTRUCTIONS,
        provider_config=role_configs["security"],
        output_schema=SpecialistSecurityPayload if supports_structured_output else None,
    )
    try:
        run = await asyncio.wait_for(_maybe_await(agent.arun(ctx.shared_prompt)), timeout=timeout)
        return _parse_specialist_security_output(_content_to_raw(run.content), ctx)
    except asyncio.TimeoutError:
        logger.warning("Security reviewer timed out after %ds", timeout)
        return SpecialistFailure(role="security-reviewer", reason="timeout")
    except Exception as exc:
        logger.warning("Security reviewer failed: %s", exc)
        return SpecialistFailure(role="security-reviewer", reason=str(exc))


async def _run_cross_repo_reviewer(
    ctx: ReviewContext,
    role_configs: dict[str, tuple[str, str, str]],
    supports_structured_output: bool,
    timeout: int,
) -> SpecialistImpactOutput | SpecialistFailure:
    """Run the isolated cross-repo impact specialist, grounded on graph warnings."""
    if not ctx.impact_result or not ctx.impact_result.warnings:
        return SpecialistImpactOutput(impact_warnings=[], raw_content="")

    agent = _build_agent(
        agent_id="cross-repo-impact-reviewer",
        instructions=CROSS_REPO_IMPACT_REVIEWER_INSTRUCTIONS,
        provider_config=role_configs["cross_repo"],
        output_schema=SpecialistImpactPayload if supports_structured_output else None,
    )
    try:
        run = await asyncio.wait_for(_maybe_await(agent.arun(ctx.shared_prompt)), timeout=timeout)
        return _parse_specialist_impact_output(_content_to_raw(run.content), ctx)
    except asyncio.TimeoutError:
        logger.warning("Cross-repo impact reviewer timed out after %ds", timeout)
        return SpecialistFailure(role="cross-repo-impact-reviewer", reason="timeout")
    except Exception as exc:
        logger.warning("Cross-repo impact reviewer failed: %s", exc)
        return SpecialistFailure(role="cross-repo-impact-reviewer", reason=str(exc))


_BUG_KEY_MODIFIERS = {
    "possible",
    "potential",
    "detected",
    "found",
    "see",
    "check",
    "review",
    "verify",
    "ensure",
    "consider",
    "note",
    "warning",
    "issue",
    "error",
    "problem",
    "bug",
    "fix",
    "todo",
    "maybe",
    "perhaps",
    "likely",
    "probably",
    "certainly",
    "definitely",
    "actually",
    "really",
    "truly",
    "surely",
    "apparently",
    "seems",
    "appears",
    "looks",
    "sounds",
    "becomes",
    "gets",
}


_BUG_TEXT_STOPWORDS = _BUG_KEY_MODIFIERS | {
    "a",
    "an",
    "and",
    "are",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}


def _bug_semantic_key(description: str) -> str:
    """Extract a loose semantic category signal that collapses wording variants."""
    words = re.findall(r"[a-zA-Z]+", description)
    for w in words:
        w_lower = w.lower()
        if len(w_lower) >= 3 and w_lower not in _BUG_KEY_MODIFIERS:
            return w_lower
    return description.lower().strip()


def _normalize_bug_token(token: str) -> str:
    """Normalize a token just enough for deterministic overlap checks."""
    normalized = token.lower()
    for suffix in ("ing", "ed", "es", "s"):
        if len(normalized) > 4 and normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def _bug_text_tokens(record: dict) -> set[str]:
    """Return informative normalized tokens from description + suggestion."""
    text = f'{record.get("description", "")} {record.get("suggestion", "")}'
    tokens = {
        _normalize_bug_token(token)
        for token in re.findall(r"[a-zA-Z]+", text)
    }
    return {token for token in tokens if len(token) >= 3 and token not in _BUG_TEXT_STOPWORDS}


def _same_bug_finding(left: dict, right: dict, *, line_tolerance: int = 30) -> bool:
    """Match the same root bug across blind passes without relying on exact lines."""
    if left.get("file") != right.get("file"):
        return False

    line_distance = abs(int(left.get("line", 0)) - int(right.get("line", 0)))
    if line_distance > line_tolerance:
        return False

    left_semantic = _bug_semantic_key(left.get("description", ""))
    right_semantic = _bug_semantic_key(right.get("description", ""))
    if left_semantic and left_semantic == right_semantic:
        return True

    shared_tokens = _bug_text_tokens(left) & _bug_text_tokens(right)
    if line_distance == 0:
        return len(shared_tokens) >= 1

    return len(shared_tokens) >= 2


def _run_judge(
    output_a: SpecialistBugOutput,
    output_b: SpecialistBugOutput,
    ctx: ReviewContext,
) -> list[dict]:
    """Deduplicate Bug Reviewer A and B outputs, return list of BugReport-shaped dicts.

    Consensus severity:
    - Same bug key found by both passes -> severity 'critical', source lists both.
    - Bug key found by only one pass -> severity 'warning', source lists detecting pass.
    """
    severity_order = {"warning": 0, "minor": 1, "major": 2, "critical": 3}

    grouped_findings: list[dict[str, Any]] = []
    bug_records = [
        (pass_id, bug.model_dump(mode="json"))
        for pass_id, output in (("bug-reviewer-a", output_a), ("bug-reviewer-b", output_b))
        for bug in output.bugs
    ]
    bug_records.sort(
        key=lambda item: (
            item[1].get("file", ""),
            int(item[1].get("line", 0)),
            item[1].get("description", ""),
            item[1].get("suggestion", ""),
            item[0],
        )
    )

    for pass_id, record in bug_records:
        matched_group = next(
            (group for group in grouped_findings if _same_bug_finding(group["record"], record)),
            None,
        )
        if matched_group is None:
            grouped_findings.append({"record": record, "passes": {pass_id}})
            continue

        matched_group["passes"].add(pass_id)
        existing = matched_group["record"]
        if severity_order.get(record["severity"], 0) > severity_order.get(existing["severity"], 0):
            existing["severity"] = record["severity"]
        for field in ("description", "suggestion"):
            incoming_value = record.get(field, "")
            if incoming_value and incoming_value not in existing.get(field, ""):
                if existing.get(field):
                    existing[field] = f'{existing[field]}; {incoming_value}'
                else:
                    existing[field] = incoming_value

    results: list[dict] = []
    for group in grouped_findings:
        record = group["record"]
        passes = group["passes"]
        if len(passes) == 2:
            record["severity"] = "critical"
            record["source"] = "bug-reviewer-a,bug-reviewer-b"
        else:
            record["severity"] = "warning"
            record["source"] = next(iter(passes))
        results.append(record)

    return results


def _ground_impact_warnings(
    parsed: list[Any],
    ctx: ReviewContext,
) -> list[Any]:
    """Discard impact warnings that are not grounded in changed paths or graph evidence."""
    if not parsed:
        return []

    changed_paths_set = set(ctx.changed_paths)
    grounded: list[Any] = []

    # Build graph evidence map: changed_file -> set of (affected_service, affected_repository)
    graph_evidence: dict[str, set[tuple[str, str]]] = {}
    if ctx.impact_result and ctx.impact_result.warnings:
        for w in ctx.impact_result.warnings:
            graph_evidence.setdefault(w.changed_file, set()).add(
                (w.affected_service, w.affected_repository)
            )

    for w in parsed:
        changed_file = getattr(w, "changed_file", "")
        if changed_file not in changed_paths_set:
            logger.warning(
                "Discarding ungrounded impact warning: changed_file=%s not in changed_paths",
                changed_file,
            )
            continue

        # If graph warnings exist, validate changed_file AND service/repo against graph evidence
        if graph_evidence:
            if changed_file not in graph_evidence:
                logger.warning(
                    "Discarding ungrounded impact warning: no graph evidence for %s",
                    changed_file,
                )
                continue
            svc = getattr(w, "affected_service", "")
            repo = getattr(w, "affected_repository", "")
            if (svc, repo) not in graph_evidence[changed_file]:
                logger.warning(
                    "Discarding ungrounded impact warning: service=%s repo=%s not in graph evidence for %s",
                    svc,
                    repo,
                    changed_file,
                )
                continue

        grounded.append(w)

    return grounded


def _ground_bug_reports(
    parsed: list[BugReport], ctx: ReviewContext, source: str
) -> list[BugReport]:
    """Discard bug findings whose file is not present in the PR diff."""
    if not parsed:
        return []

    changed_paths_set = set(ctx.changed_paths)
    grounded: list[BugReport] = []
    for bug in parsed:
        if bug.file not in changed_paths_set:
            logger.warning(
                "Discarding ungrounded %s bug: file=%s not in changed_paths",
                source,
                bug.file,
            )
            continue
        grounded.append(bug)
    return grounded


def _ground_specialist_bug_output(
    output: SpecialistBugOutput, ctx: ReviewContext
) -> SpecialistBugOutput:
    output.bugs = _ground_bug_reports(output.bugs, ctx, output.provider or "bug-reviewer")
    return output


def _merge_bug_dicts(existing: dict, incoming: dict) -> None:
    """Merge *incoming* bug into *existing*, escalating severity and combining text."""
    severity_order = {"minor": 0, "major": 1, "critical": 2}
    if severity_order.get(incoming.get("severity"), 0) > severity_order.get(
        existing.get("severity"), 0
    ):
        existing["severity"] = incoming["severity"]

    for field in ("description", "suggestion"):
        existing_val = existing.get(field, "")
        incoming_val = incoming.get(field, "")
        if incoming_val and incoming_val != existing_val:
            if existing_val:
                # Avoid concatenating duplicate text
                if incoming_val not in existing_val and existing_val not in incoming_val:
                    existing[field] = f"{existing_val}; {incoming_val}"
            else:
                existing[field] = incoming_val

    # Preserve security category over bug; keep first non-empty source
    incoming_category = incoming.get("category", "bug")
    if incoming_category == "security" or existing.get("category", "bug") == "security":
        existing["category"] = "security"
    existing_source = existing.get("source", "")
    incoming_source = incoming.get("source", "")
    if incoming_source and not existing_source:
        existing["source"] = incoming_source
    elif incoming_category == "security" and incoming_source:
        existing["source"] = incoming_source


def _synthesize(
    judged_bugs: list[dict],
    security_bugs: list[BugReport],
    impact_warnings: list,
    ctx: ReviewContext,
) -> ReviewOutput:
    """Merge all specialist outputs into a single ReviewOutput."""

    # Combine judged + security bugs, merging by (file, line) and escalating severity.
    merged: dict[tuple[str, int], dict] = {}
    for bug_dict in judged_bugs:
        key = (bug_dict["file"], bug_dict["line"])
        bug_dict.setdefault("category", "bug")
        if not bug_dict.get("source"):
            bug_dict["source"] = "bug-reviewer-a,bug-reviewer-b"
        if key not in merged:
            merged[key] = dict(bug_dict)
        else:
            _merge_bug_dicts(merged[key], bug_dict)

    for bug in security_bugs:
        key = (bug.file, bug.line)
        bug_dict = bug.model_dump(mode="json")
        bug_dict["category"] = "security"
        bug_dict["source"] = bug_dict.get("source") or "security-reviewer"
        if key not in merged:
            merged[key] = bug_dict
        else:
            _merge_bug_dicts(merged[key], bug_dict)

    all_bugs = [BugReport(**d) for d in merged.values()]

    # Determine approval
    has_critical = any(b.severity == "critical" for b in all_bugs)
    has_high_impact = any(getattr(w, "severity", "") == "high" for w in impact_warnings)
    approved = not has_critical and not has_high_impact

    # Build summary
    if all_bugs:
        bug_summaries = []
        for severity in ["critical", "major", "minor", "warning"]:
            count = sum(1 for b in all_bugs if b.severity == severity)
            if count:
                bug_summaries.append(f"{count} {severity} bug(s)")
        bug_text = f"Found {', '.join(bug_summaries)}."
    else:
        bug_text = "No bugs detected."

    summary = (
        f"PR review complete. {bug_text} "
        f"Security: {len(security_bugs)} issue(s). "
        f"Impact: {len(impact_warnings)} warning(s). "
        f"Recommendation: {'approved' if approved else 'changes requested'}."
    )

    return ReviewOutput(
        summary=summary,
        bugs=all_bugs,
        approved=approved,
        impact_warnings=impact_warnings,
    )


def _build_review_health(
    bug_failed: bool,
    bug_no_valid_output: bool,
    security_failed: bool,
    cross_repo_failed: bool,
    cross_repo_skipped: bool,
) -> ReviewHealth:
    """Build review health from specialist execution outcomes."""
    warnings: list[str] = []

    if bug_failed:
        warnings.append("Bug reviewers failed or timed out.")
    elif bug_no_valid_output:
        warnings.append("Bug reviewers produced no valid output.")

    if security_failed:
        warnings.append("Security reviewer failed or timed out.")

    if cross_repo_failed:
        warnings.append("Cross-repo impact reviewer failed or timed out.")
    elif cross_repo_skipped:
        warnings.append("Cross-repo impact reviewer skipped (no graph evidence).")

    # For health classification, parse failures count as degraded; empty but valid output does not
    has_parse_failure = bug_failed or security_failed or cross_repo_failed
    has_skip = cross_repo_skipped and not has_parse_failure

    if has_parse_failure:
        return ReviewHealth(status="degraded", warnings=warnings)
    if has_skip:
        return ReviewHealth(status="partial", warnings=warnings)
    return ReviewHealth(status="complete", warnings=warnings)


def _merge_impact_warnings(
    reviewer_warnings: list[Any],
    graph_warnings: list[Any],
) -> list[Any]:
    """Merge reviewer and graph warnings, deduping by (changed_file, affected_service).

    When two warnings share the same (changed_file, affected_service) pair,
    keep one entry and escalate to the higher severity.
    """
    severity_order = {"low": 0, "medium": 1, "high": 2}
    merged: dict[tuple[str, str], Any] = {}

    for w in [*reviewer_warnings, *graph_warnings]:
        key = (getattr(w, "changed_file", ""), getattr(w, "affected_service", ""))
        if key not in merged:
            merged[key] = w
            continue
        existing = merged[key]
        existing_sev = severity_order.get(getattr(existing, "severity", ""), 0)
        incoming_sev = severity_order.get(getattr(w, "severity", ""), 0)
        if incoming_sev > existing_sev:
            merged[key] = w

    return list(merged.values())


async def arun_multi_agent_review(
    owner: str,
    repo: str,
    pr_number: int,
    role_configs: dict[str, tuple[str, str, str]],
    github_token: str = "",
    supports_structured_output: bool = True,
) -> ReviewOutput:
    """Async core for the multi-agent review pipeline."""
    Config._validate_role_configs(role_configs)

    # Step 1: fetch once
    diff_text, head_sha, pr_title = fetch_pr_data(owner, repo, pr_number, github_token=github_token)

    # Step 2: build context
    ctx = build_review_context(
        owner=owner,
        repo=repo,
        pr_number=pr_number,
        head_sha=head_sha,
        pr_title=pr_title,
        diff_text=diff_text,
        github_token=github_token,
    )

    # Safe context-delivery diagnostics (lengths/counts only — no diff body or secrets)
    diagnostics = _safe_context_summary(
        diff_text=ctx.diff_text,
        shared_prompt=ctx.shared_prompt,
        changed_paths=ctx.changed_paths,
    )
    logger.info("Review context diagnostics: %s", diagnostics)

    # Step 3: fan out all specialists concurrently
    timeout = Config.REVIEW_SPECIALIST_TIMEOUT_SECONDS
    logger.debug("Specialist timeout configured: %s seconds", timeout)

    # Log role-to-model resolution without exposing secrets
    for role, (model_id, base_url, _api_key) in role_configs.items():
        logger.info(
            "Review role %s -> model=%s base_url_host=%s",
            role,
            model_id,
            base_url,
        )

    bug_result, security_result, cross_repo_result = await asyncio.gather(
        asyncio.wait_for(
            _run_bug_reviewers(ctx, role_configs, supports_structured_output), timeout=timeout
        ),
        asyncio.wait_for(
            _run_security_reviewer(ctx, role_configs, supports_structured_output, timeout=timeout),
            timeout=timeout,
        ),
        asyncio.wait_for(
            _run_cross_repo_reviewer(
                ctx, role_configs, supports_structured_output, timeout=timeout
            ),
            timeout=timeout,
        ),
        return_exceptions=True,
    )

    # Normalize bug reviewer pair result
    bug_a = SpecialistBugOutput(bugs=[])
    bug_b = SpecialistBugOutput(bugs=[])
    bug_failed = False
    if isinstance(bug_result, BaseException) and not isinstance(bug_result, SpecialistFailure):
        logger.warning("Bug reviewers raised exception: %s", bug_result)
        bug_failed = True
    elif isinstance(bug_result, SpecialistFailure):
        logger.warning("Bug reviewers failed: %s", bug_result.reason)
        bug_failed = True
    else:
        bug_a, bug_b = bug_result

    bug_no_valid_output = (bug_a.parse_failed or not bug_a.raw_content) and (
        bug_b.parse_failed or not bug_b.raw_content
    )

    # Normalize Security result
    security_bugs: list[BugReport] = []
    security_failed = False
    if isinstance(security_result, BaseException) and not isinstance(
        security_result, SpecialistFailure
    ):
        logger.warning("Security reviewer raised exception: %s", security_result)
        security_failed = True
    elif isinstance(security_result, SpecialistFailure):
        logger.warning("Security reviewer failed: %s", security_result.reason)
        security_failed = True
    else:
        security_bugs = security_result.bugs

    # Normalize Cross-Repo result
    impact_warnings: list = []
    cross_repo_failed = False
    if isinstance(cross_repo_result, BaseException) and not isinstance(
        cross_repo_result, SpecialistFailure
    ):
        logger.warning("Cross-repo impact reviewer raised exception: %s", cross_repo_result)
        cross_repo_failed = True
    elif isinstance(cross_repo_result, SpecialistFailure):
        logger.warning("Cross-repo impact reviewer failed: %s", cross_repo_result.reason)
        cross_repo_failed = True
    else:
        impact_warnings = cross_repo_result.impact_warnings

    # Ground parsed impact warnings against changed paths / graph evidence
    bug_a = _ground_specialist_bug_output(bug_a, ctx)
    bug_b = _ground_specialist_bug_output(bug_b, ctx)
    security_bugs = _ground_bug_reports(security_bugs, ctx, "security-reviewer")
    impact_warnings = _ground_impact_warnings(impact_warnings, ctx)

    # Merge graph-derived warnings with reviewer warnings, deduping semantically
    graph_warnings = []
    if ctx.impact_result and ctx.impact_result.warnings:
        graph_warnings = list(ctx.impact_result.warnings)
    impact_warnings = _merge_impact_warnings(impact_warnings, graph_warnings)

    cross_repo_skipped = (
        not cross_repo_failed
        and isinstance(cross_repo_result, SpecialistImpactOutput)
        and cross_repo_result.raw_content == ""
    )

    review_health = _build_review_health(
        bug_failed=bug_failed,
        bug_no_valid_output=bug_no_valid_output,
        security_failed=security_failed,
        cross_repo_failed=cross_repo_failed,
        cross_repo_skipped=cross_repo_skipped,
    )

    # If every specialist failed or produced no valid output, degrade instead of misrepresenting as clean
    all_specialists_failed = (
        (bug_failed or bug_no_valid_output)
        and security_failed
        and (cross_repo_failed or cross_repo_skipped)
    )
    if all_specialists_failed:
        logger.warning(
            "All specialists failed or produced no valid output; returning degraded ReviewOutput"
        )
        degraded = _parse_failure_result(ctx.impact_result)
        degraded.review_health = review_health
        return degraded

    # Step 4: judge/deduper (failure degrades to _parse_failure_result)
    try:
        judged_bugs: list[dict] = _run_judge(bug_a, bug_b, ctx)
    except Exception as exc:
        logger.warning("Judge failed: %s", exc)
        degraded = _parse_failure_result(ctx.impact_result)
        degraded.review_health = review_health
        return degraded

    # Step 5: synthesizer (failure degrades to _parse_failure_result)
    try:
        result = _synthesize(judged_bugs, security_bugs, impact_warnings, ctx)
    except Exception as exc:
        logger.warning("Synthesizer failed: %s", exc)
        degraded = _parse_failure_result(ctx.impact_result)
        degraded.review_health = review_health
        return degraded

    result.review_health = review_health

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


def run_multi_agent_review(
    owner: str,
    repo: str,
    pr_number: int,
    role_configs: dict[str, tuple[str, str, str]],
    github_token: str = "",
    supports_structured_output: bool = True,
) -> ReviewOutput:
    """Sync wrapper preserving the current public API boundary."""
    return _run_coro_sync(
        arun_multi_agent_review(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            role_configs=role_configs,
            github_token=github_token,
            supports_structured_output=supports_structured_output,
        )
    )
