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
from collections.abc import Iterable
from typing import Any

from agno.agent import Agent
from agno.models.openai.like import OpenAILike
from agno.team import Team

from src.core.config import Config
from src.core.observability import render_prompt
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
    SpecialistFailure,
    SpecialistImpactOutput,
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


def _parse_specialist_bug_output(raw: str, role: str, ctx: ReviewContext) -> SpecialistBugOutput:
    try:
        data = json.loads(raw)
        out = SpecialistBugOutput(**data)
    except Exception:
        _log_full_llm_response(raw, ctx.owner, ctx.repo, ctx.pr_number)
        return SpecialistBugOutput(bugs=[], provider=role, raw_content=raw, parse_failed=True)
    out.provider = role
    out.raw_content = raw
    return out


def _parse_specialist_security_output(
    raw: str, ctx: ReviewContext
) -> SpecialistSecurityOutput | SpecialistFailure:
    try:
        data = json.loads(raw)
        return SpecialistSecurityOutput(**data, raw_content=raw)
    except Exception as exc:
        _log_full_llm_response(raw, ctx.owner, ctx.repo, ctx.pr_number)
        return SpecialistFailure(role="security-reviewer", reason=f"parse failure: {exc}")


def _parse_specialist_impact_output(
    raw: str, ctx: ReviewContext
) -> SpecialistImpactOutput | SpecialistFailure:
    try:
        data = json.loads(raw)
        return SpecialistImpactOutput(**data, raw_content=raw)
    except Exception as exc:
        _log_full_llm_response(raw, ctx.owner, ctx.repo, ctx.pr_number)
        return SpecialistFailure(role="cross-repo-impact-reviewer", reason=f"parse failure: {exc}")


def _iter_team_messages(run: Any) -> Iterable[Any]:
    """Yield team/member messages from either mocked or real Agno responses.

    Prefer ``member_responses`` (RunOutput objects with reliable ``agent_id``)
    over ``messages`` (Message objects where the agent identifier is less
    predictable). This aligns with real Agno Team behaviour.
    """
    for attr in ("member_responses", "messages"):
        messages = getattr(run, attr, None)
        if messages:
            yield from messages
            return


async def _run_bug_reviewers(
    ctx: ReviewContext,
    provider_config: tuple[str, str, str],
    supports_structured_output: bool,
) -> tuple[SpecialistBugOutput, SpecialistBugOutput]:
    """Run blind Bug Reviewer A/B using an Agno Team broadcast."""
    schema = SpecialistBugOutput if supports_structured_output else None
    agent_a = _build_agent(
        agent_id="bug-reviewer-a",
        instructions=BUG_REVIEWER_INSTRUCTIONS,
        provider_config=provider_config,
        output_schema=schema,
    )
    agent_b = _build_agent(
        agent_id="bug-reviewer-b",
        instructions=BUG_REVIEWER_INSTRUCTIONS,
        provider_config=provider_config,
        output_schema=schema,
    )

    leader_prompt = render_prompt("bug_review_team_leader", shared_prompt=ctx.shared_prompt)
    team = Team(
        id="bug-review-team",
        mode="broadcast",
        members=[agent_a, agent_b],
        instructions=leader_prompt,
        share_member_interactions=False,
        show_members_responses=True,
    )

    async def collect_outputs(run_result: Any) -> dict[str, SpecialistBugOutput]:
        collected: dict[str, SpecialistBugOutput] = {}
        for msg in _iter_team_messages(run_result):
            agent_id = (
                getattr(msg, "agent_id", None)
                or getattr(msg, "agent_name", None)
                or getattr(msg, "name", None)
            )
            if agent_id not in {"bug-reviewer-a", "bug-reviewer-b"}:
                continue
            content = getattr(msg, "content", "")
            raw = _content_to_raw(content)
            collected[agent_id] = _parse_specialist_bug_output(raw, agent_id, ctx)
        return collected

    outputs: dict[str, SpecialistBugOutput] = {}
    if hasattr(team, "arun"):
        run = await _maybe_await(team.arun(ctx.shared_prompt))
        outputs = await collect_outputs(run)

    # Mocked teams and some Agno versions expose only sync `run`; fallback when
    # async output didn't include member responses.
    if len(outputs) < 2 and hasattr(team, "run"):
        run = await asyncio.to_thread(team.run, ctx.shared_prompt)
        outputs = await collect_outputs(run)

    if len(outputs) < 2:
        logger.warning("Expected 2 bug reviewer outputs, got %d", len(outputs))
    for agent_id in ("bug-reviewer-a", "bug-reviewer-b"):
        if agent_id not in outputs:
            outputs[agent_id] = SpecialistBugOutput(bugs=[], provider=agent_id, raw_content="")
    return outputs["bug-reviewer-a"], outputs["bug-reviewer-b"]


async def _run_security_reviewer(
    ctx: ReviewContext,
    provider_config: tuple[str, str, str],
    supports_structured_output: bool,
    timeout: int,
) -> SpecialistSecurityOutput | SpecialistFailure:
    """Run the isolated security specialist."""
    agent = _build_agent(
        agent_id="security-reviewer",
        instructions=SECURITY_REVIEWER_INSTRUCTIONS,
        provider_config=provider_config,
        output_schema=SpecialistSecurityOutput if supports_structured_output else None,
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
    provider_config: tuple[str, str, str],
    supports_structured_output: bool,
    timeout: int,
) -> SpecialistImpactOutput | SpecialistFailure:
    """Run the isolated cross-repo impact specialist, grounded on graph warnings."""
    if not ctx.impact_result or not ctx.impact_result.warnings:
        return SpecialistImpactOutput(impact_warnings=[], raw_content="")

    agent = _build_agent(
        agent_id="cross-repo-impact-reviewer",
        instructions=CROSS_REPO_IMPACT_REVIEWER_INSTRUCTIONS,
        provider_config=provider_config,
        output_schema=SpecialistImpactOutput if supports_structured_output else None,
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


def _bug_semantic_key(description: str) -> str:
    """Extract a loose semantic category signal that collapses wording variants."""
    words = re.findall(r"[a-zA-Z]+", description)
    for w in words:
        w_lower = w.lower()
        if len(w_lower) >= 3 and w_lower not in _BUG_KEY_MODIFIERS:
            return w_lower
    return description.lower().strip()


def _run_judge(
    output_a: SpecialistBugOutput,
    output_b: SpecialistBugOutput,
    ctx: ReviewContext,
) -> list[dict]:
    """Deduplicate Bug Reviewer A and B outputs, return list of BugReport-shaped dicts."""
    all_bugs: list[SpecialistBugOutput] = [output_a, output_b]

    bug_records: list[dict] = []
    for specialist in all_bugs:
        for bug in specialist.bugs:
            bug_records.append(bug.model_dump(mode="json"))

    # Deterministic dedupe key is (file, line, semantic_key) so same-location
    # findings collapse when wording variants describe the same bug type,
    # but distinct bugs on the same line are preserved.
    seen: dict[tuple[str, int, str], dict] = {}
    for record in bug_records:
        key = (record["file"], record["line"], _bug_semantic_key(record["description"]))
        if key not in seen:
            seen[key] = record
        else:
            # Escalate severity on conflict
            severity_order = {"minor": 0, "major": 1, "critical": 2}
            existing = seen[key]
            if severity_order.get(record["severity"], 0) > severity_order.get(
                existing["severity"], 0
            ):
                seen[key] = record

    return list(seen.values())


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
            bug_dict["source"] = "bug-reviewer-team"
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
        for severity in ["critical", "major", "minor"]:
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
    provider_config: tuple[str, str, str],
    github_token: str = "",
    supports_structured_output: bool = True,
) -> ReviewOutput:
    """Async core for the multi-agent review pipeline."""
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

    # Step 3: fan out all specialists concurrently
    timeout = Config.REVIEW_SPECIALIST_TIMEOUT_SECONDS
    logger.debug("Specialist timeout configured: %s seconds", timeout)

    bug_result, security_result, cross_repo_result = await asyncio.gather(
        asyncio.wait_for(
            _run_bug_reviewers(ctx, provider_config, supports_structured_output), timeout=timeout
        ),
        _run_security_reviewer(ctx, provider_config, supports_structured_output, timeout=timeout),
        _run_cross_repo_reviewer(ctx, provider_config, supports_structured_output, timeout=timeout),
        return_exceptions=True,
    )

    # Normalize Bug Team result
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
    provider_config: tuple[str, str, str],
    github_token: str = "",
    supports_structured_output: bool = True,
) -> ReviewOutput:
    """Sync wrapper preserving the current public API boundary."""
    return _run_coro_sync(
        arun_multi_agent_review(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            provider_config=provider_config,
            github_token=github_token,
            supports_structured_output=supports_structured_output,
        )
    )
