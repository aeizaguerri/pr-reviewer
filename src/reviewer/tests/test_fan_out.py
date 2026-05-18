"""RED-phase tests: parallel fan-out orchestration (task 3.1 fixes)."""

import asyncio
from unittest.mock import patch

import pytest

from src.knowledge.models import ImpactWarning
from src.reviewer.models import (
    BugReport,
    ReviewContext,
    ReviewOutput,
    SpecialistBugOutput,
    SpecialistImpactOutput,
    SpecialistSecurityOutput,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


class TestFanOut:
    _PROVIDER_CONFIG = ("my-model", "https://api.example.com/v1", "sk-test")

    def _make_context(self) -> ReviewContext:
        return ReviewContext(
            owner="owner",
            repo="repo",
            pr_number=1,
            head_sha="abc123",
            pr_title="Fix bug",
            diff_text="### file.py\n@@ -1 +1 @@\n-patch",
            changed_paths=["file.py"],
            shared_prompt="test prompt",
        )

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_specialists_start_concurrently(self, mock_cross, mock_sec, mock_bug):
        """Bug Team, Security, and Cross-Repo must start in the same scheduling window."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        bug_started = asyncio.Event()
        sec_started = asyncio.Event()
        cross_started = asyncio.Event()

        async def slow_bug(*args, **kwargs):
            bug_started.set()
            # Yield until the other specialists have also started
            while not (sec_started.is_set() and cross_started.is_set()):
                await asyncio.sleep(0)
            return (
                SpecialistBugOutput(bugs=[]),
                SpecialistBugOutput(bugs=[]),
            )

        async def slow_sec(*args, **kwargs):
            sec_started.set()
            while not bug_started.is_set():
                await asyncio.sleep(0)
            return SpecialistSecurityOutput(bugs=[])

        async def slow_cross(*args, **kwargs):
            cross_started.set()
            while not bug_started.is_set():
                await asyncio.sleep(0)
            return SpecialistImpactOutput(impact_warnings=[])

        mock_bug.side_effect = slow_bug
        mock_sec.side_effect = slow_sec
        mock_cross.side_effect = slow_cross

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                result = await asyncio.wait_for(
                    arun_multi_agent_review("owner", "repo", 1, self._PROVIDER_CONFIG),
                    timeout=1.0,
                )

        assert isinstance(result, ReviewOutput)

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_bug_team_failure_returns_valid_output(self, mock_cross, mock_sec, mock_bug):
        """Bug Team crash must degrade to empty bugs, not propagate an exception."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        mock_bug.side_effect = RuntimeError("bug team exploded")
        mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
        mock_cross.return_value = SpecialistImpactOutput(impact_warnings=[])

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                result = await arun_multi_agent_review("owner", "repo", 1, self._PROVIDER_CONFIG)

        assert isinstance(result, ReviewOutput)
        assert len(result.bugs) == 0
        assert "No bugs detected" in result.summary
        assert "Recommendation: approved" in result.summary

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    @patch("src.reviewer.orchestrator._run_judge")
    async def test_judge_failure_degrades_to_parse_failure_result(
        self, mock_judge, mock_cross, mock_sec, mock_bug
    ):
        """Judge exception must produce degraded ReviewOutput via _parse_failure_result."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        mock_bug.return_value = (
            SpecialistBugOutput(bugs=[]),
            SpecialistBugOutput(bugs=[]),
        )
        mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
        mock_cross.return_value = SpecialistImpactOutput(impact_warnings=[])
        mock_judge.side_effect = RuntimeError("judge failed")

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                result = await arun_multi_agent_review("owner", "repo", 1, self._PROVIDER_CONFIG)

        assert isinstance(result, ReviewOutput)
        assert result.summary.startswith("Error:")
        assert result.approved is False
        assert len(result.bugs) == 0

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    @patch("src.reviewer.orchestrator._synthesize")
    async def test_synthesizer_failure_degrades_to_parse_failure_result(
        self, mock_synth, mock_cross, mock_sec, mock_bug
    ):
        """Synthesizer exception must produce degraded ReviewOutput via _parse_failure_result."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        mock_bug.return_value = (
            SpecialistBugOutput(bugs=[]),
            SpecialistBugOutput(bugs=[]),
        )
        mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
        mock_cross.return_value = SpecialistImpactOutput(impact_warnings=[])
        mock_synth.side_effect = RuntimeError("synth failed")

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                result = await arun_multi_agent_review("owner", "repo", 1, self._PROVIDER_CONFIG)

        assert isinstance(result, ReviewOutput)
        assert result.summary.startswith("Error:")
        assert result.approved is False
        assert len(result.bugs) == 0

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_unsupported_impact_claims_are_discarded(self, mock_cross, mock_sec, mock_bug):
        """Cross-repo warnings with changed_file outside changed_paths must be filtered out."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        mock_bug.return_value = (
            SpecialistBugOutput(bugs=[]),
            SpecialistBugOutput(bugs=[]),
        )
        mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
        mock_cross.return_value = SpecialistImpactOutput(
            impact_warnings=[
                ImpactWarning(
                    changed_file="nonexistent.py",
                    changed_entity="E",
                    affected_service="svc",
                    affected_repository="repo",
                    relationship_type="CONSUMES",
                    severity="high",
                    description="unsupported",
                ),
                ImpactWarning(
                    changed_file="file.py",
                    changed_entity="E",
                    affected_service="svc",
                    affected_repository="repo",
                    relationship_type="CONSUMES",
                    severity="medium",
                    description="supported",
                ),
            ]
        )

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                result = await arun_multi_agent_review("owner", "repo", 1, self._PROVIDER_CONFIG)

        assert isinstance(result, ReviewOutput)
        assert len(result.impact_warnings) == 1
        assert result.impact_warnings[0].changed_file == "file.py"
        assert result.impact_warnings[0].severity == "medium"

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_one_bug_reviewer_missing_final_output_preserved(
        self, mock_cross, mock_sec, mock_bug
    ):
        """FAIL-001: surviving Bug reviewer output must reach final ReviewOutput."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        real_bug = BugReport(
            file="src/a.py",
            line=10,
            severity="major",
            description="bug",
            suggestion="fix",
        )
        mock_bug.return_value = (
            SpecialistBugOutput(bugs=[]),
            SpecialistBugOutput(bugs=[real_bug]),
        )
        mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
        mock_cross.return_value = SpecialistImpactOutput(impact_warnings=[])

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                result = await arun_multi_agent_review(
                    "owner", "repo", 1, self._PROVIDER_CONFIG
                )

        assert isinstance(result, ReviewOutput)
        assert len(result.bugs) == 1
        assert result.bugs[0].file == "src/a.py"

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_bug_team_timeout_degrades(self, mock_cross, mock_sec, mock_bug):
        """FAIL-003: Bug Team exceeding timeout must degrade to empty bugs, not hang."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        async def slow_bug(*args, **kwargs):
            await asyncio.sleep(10)

        mock_bug.side_effect = slow_bug
        mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
        mock_cross.return_value = SpecialistImpactOutput(impact_warnings=[])

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                with patch("src.reviewer.orchestrator.Config") as mock_cfg:
                    mock_cfg.REVIEW_SPECIALIST_TIMEOUT_SECONDS = 0.01
                    result = await asyncio.wait_for(
                        arun_multi_agent_review("owner", "repo", 1, self._PROVIDER_CONFIG),
                        timeout=1.0,
                    )

        assert isinstance(result, ReviewOutput)
        assert len(result.bugs) == 0

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_timeout_is_passed_to_specialists(self, mock_cross, mock_sec, mock_bug):
        """Task 3.1: timeout from Config reaches async specialists."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        mock_bug.return_value = (
            SpecialistBugOutput(bugs=[]),
            SpecialistBugOutput(bugs=[]),
        )
        mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
        mock_cross.return_value = SpecialistImpactOutput(impact_warnings=[])

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                with patch("src.reviewer.orchestrator.Config") as mock_cfg:
                    mock_cfg.REVIEW_SPECIALIST_TIMEOUT_SECONDS = 99
                    await arun_multi_agent_review("owner", "repo", 1, self._PROVIDER_CONFIG)

        # Security and Cross-Repo receive timeout as positional arg
        assert mock_sec.call_args[1]["timeout"] == 99
        assert mock_cross.call_args[1]["timeout"] == 99

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_unsupported_service_repo_claims_discarded(self, mock_cross, mock_sec, mock_bug):
        """CRI-002: changed_file valid but affected_service/repo unsupported by graph evidence must be discarded."""
        from src.reviewer.orchestrator import arun_multi_agent_review
        from src.knowledge.models import ImpactResult

        mock_bug.return_value = (
            SpecialistBugOutput(bugs=[]),
            SpecialistBugOutput(bugs=[]),
        )
        mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
        mock_cross.return_value = SpecialistImpactOutput(
            impact_warnings=[
                ImpactWarning(
                    changed_file="file.py",
                    changed_entity="E",
                    affected_service="supported-svc",
                    affected_repository="supported-repo",
                    relationship_type="CONSUMES",
                    severity="medium",
                    description="supported",
                ),
                ImpactWarning(
                    changed_file="file.py",
                    changed_entity="E",
                    affected_service="hallucinated-svc",
                    affected_repository="hallucinated-repo",
                    relationship_type="CONSUMES",
                    severity="high",
                    description="unsupported service/repo",
                ),
            ]
        )

        ctx = self._make_context()
        ctx.impact_result = ImpactResult(
            warnings=[
                ImpactWarning(
                    changed_file="file.py",
                    changed_entity="E",
                    affected_service="supported-svc",
                    affected_repository="supported-repo",
                    relationship_type="CONSUMES",
                    severity="low",
                    description="graph evidence",
                )
            ]
        )

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = ctx
                result = await arun_multi_agent_review("owner", "repo", 1, self._PROVIDER_CONFIG)

        assert isinstance(result, ReviewOutput)
        assert len(result.impact_warnings) == 1
        assert result.impact_warnings[0].affected_service == "supported-svc"
        assert result.impact_warnings[0].affected_repository == "supported-repo"

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_all_specialists_failure_degrades(self, mock_cross, mock_sec, mock_bug):
        """FAIL-003/FAIL-004: all specialists failing must return degraded ReviewOutput, not approved clean."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        mock_bug.side_effect = RuntimeError("bug team exploded")
        mock_sec.side_effect = RuntimeError("security exploded")
        mock_cross.side_effect = RuntimeError("cross-repo exploded")

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                result = await arun_multi_agent_review("owner", "repo", 1, self._PROVIDER_CONFIG)

        assert isinstance(result, ReviewOutput)
        assert result.approved is False
        assert result.summary.startswith("Error:")
        assert len(result.bugs) == 0

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_bug_and_security_fail_cross_repo_skipped_degrades(
        self, mock_cross, mock_sec, mock_bug
    ):
        """BUG-R2-1: Bug Team exception + Security failure + no graph evidence => degraded non-approved output."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        mock_bug.side_effect = RuntimeError("bug team exploded")
        mock_sec.side_effect = RuntimeError("security exploded")
        mock_cross.return_value = SpecialistImpactOutput(impact_warnings=[], raw_content="")

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                result = await arun_multi_agent_review(
                    "owner", "repo", 1, self._PROVIDER_CONFIG
                )

        assert isinstance(result, ReviewOutput)
        assert result.approved is False
        assert result.summary.startswith("Error:")
        assert len(result.bugs) == 0

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_both_bug_malformed_security_fail_cross_repo_fail_degrades(
        self, mock_cross, mock_sec, mock_bug
    ):
        """BUG-R2-2: Both Bug reviewers malformed + Security failure + Cross-Repo failure/skipped => degraded non-approved output."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        mock_bug.return_value = (
            SpecialistBugOutput(
                bugs=[], provider="bug-reviewer-a", raw_content="bad json", parse_failed=True
            ),
            SpecialistBugOutput(
                bugs=[], provider="bug-reviewer-b", raw_content="also bad", parse_failed=True
            ),
        )
        mock_sec.side_effect = RuntimeError("security exploded")
        mock_cross.side_effect = RuntimeError("cross-repo exploded")

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                result = await arun_multi_agent_review(
                    "owner", "repo", 1, self._PROVIDER_CONFIG
                )

        assert isinstance(result, ReviewOutput)
        assert result.approved is False
        assert result.summary.startswith("Error:")
        assert len(result.bugs) == 0

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_one_valid_bug_prevents_false_degradation(self, mock_cross, mock_sec, mock_bug):
        """BUG-R2-3: One valid bug reviewer output must prevent broad-failure degradation even if others fail."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        real_bug = BugReport(
            file="src/a.py",
            line=10,
            severity="critical",
            description="bug",
            suggestion="fix",
        )
        mock_bug.return_value = (
            SpecialistBugOutput(
                bugs=[real_bug], provider="bug-reviewer-a", raw_content='{"bugs": [...]}'
            ),
            SpecialistBugOutput(
                bugs=[], provider="bug-reviewer-b", raw_content="bad json", parse_failed=True
            ),
        )
        mock_sec.side_effect = RuntimeError("security exploded")
        mock_cross.side_effect = RuntimeError("cross-repo exploded")

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                result = await arun_multi_agent_review(
                    "owner", "repo", 1, self._PROVIDER_CONFIG
                )

        assert isinstance(result, ReviewOutput)
        # Must NOT be a parse-failure degraded output
        assert not result.summary.startswith("Error:")
        # The valid bug should still surface
        assert len(result.bugs) == 1
        assert result.bugs[0].file == "src/a.py"
        assert result.approved is False

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_impact_warnings_deduped_by_file_and_service(self, mock_cross, mock_sec, mock_bug):
        """SYN-003: duplicate impact warnings by (changed_file, affected_service) must merge/escalate."""
        from src.reviewer.orchestrator import arun_multi_agent_review
        from src.knowledge.models import ImpactResult

        mock_bug.return_value = (
            SpecialistBugOutput(bugs=[]),
            SpecialistBugOutput(bugs=[]),
        )
        mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
        mock_cross.return_value = SpecialistImpactOutput(
            impact_warnings=[
                ImpactWarning(
                    changed_file="file.py",
                    changed_entity="E1",
                    affected_service="svc-a",
                    affected_repository="repo-a",
                    relationship_type="CONSUMES",
                    severity="medium",
                    description="from reviewer",
                ),
            ]
        )

        ctx = self._make_context()
        ctx.impact_result = ImpactResult(
            warnings=[
                ImpactWarning(
                    changed_file="file.py",
                    changed_entity="E2",
                    affected_service="svc-a",
                    affected_repository="repo-a",
                    relationship_type="CONSUMES",
                    severity="high",
                    description="from graph",
                ),
                ImpactWarning(
                    changed_file="file.py",
                    changed_entity="E3",
                    affected_service="svc-b",
                    affected_repository="repo-b",
                    relationship_type="PRODUCES",
                    severity="low",
                    description="distinct service",
                ),
            ]
        )

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = ctx
                result = await arun_multi_agent_review("owner", "repo", 1, self._PROVIDER_CONFIG)

        assert isinstance(result, ReviewOutput)
        # svc-a appears twice (reviewer + graph) → deduped to one, severity escalated to high
        # svc-b appears once
        assert len(result.impact_warnings) == 2
        svc_a = [w for w in result.impact_warnings if w.affected_service == "svc-a"]
        svc_b = [w for w in result.impact_warnings if w.affected_service == "svc-b"]
        assert len(svc_a) == 1
        assert svc_a[0].severity == "high"
        assert len(svc_b) == 1

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_orchestrator_builds_degraded_health_on_specialist_failure(self, mock_cross, mock_sec, mock_bug):
        """2.5: specialist failures produce degraded review health."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        mock_bug.side_effect = RuntimeError("bug team exploded")
        mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
        mock_cross.return_value = SpecialistImpactOutput(impact_warnings=[])

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                result = await arun_multi_agent_review("owner", "repo", 1, self._PROVIDER_CONFIG)

        assert isinstance(result, ReviewOutput)
        assert result.review_health is not None
        assert result.review_health.status == "degraded"
        assert any("bug" in w.lower() for w in result.review_health.warnings)

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator._run_bug_reviewers")
    @patch("src.reviewer.orchestrator._run_security_reviewer")
    @patch("src.reviewer.orchestrator._run_cross_repo_reviewer")
    async def test_orchestrator_builds_partial_health_on_specialist_skip(self, mock_cross, mock_sec, mock_bug):
        """2.6: cross-repo skipped (no graph evidence) produces partial health."""
        from src.reviewer.orchestrator import arun_multi_agent_review

        mock_bug.return_value = (
            SpecialistBugOutput(bugs=[]),
            SpecialistBugOutput(bugs=[]),
        )
        mock_sec.return_value = SpecialistSecurityOutput(bugs=[])
        mock_cross.return_value = SpecialistImpactOutput(impact_warnings=[], raw_content="")

        with patch(
            "src.reviewer.orchestrator.fetch_pr_data", return_value=("diff", "sha", "title")
        ):
            with patch("src.reviewer.orchestrator.build_review_context") as mock_ctx:
                mock_ctx.return_value = self._make_context()
                result = await arun_multi_agent_review("owner", "repo", 1, self._PROVIDER_CONFIG)

        assert isinstance(result, ReviewOutput)
        assert result.review_health is not None
        assert result.review_health.status == "partial"
        assert any("cross-repo" in w.lower() for w in result.review_health.warnings)
