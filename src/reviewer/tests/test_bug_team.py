"""RED-phase tests: Bug Reviewer A/B direct async execution (tasks 2.1, 2.2)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.reviewer.models import BugReport, ReviewContext, SpecialistBugOutput


@pytest.fixture
def anyio_backend():
    return "asyncio"


class TestBugReviewers:
    _PROVIDER_CONFIG = ("my-model", "https://api.example.com/v1", "sk-test")
    _ROLE_CONFIGS = {
        "bug": _PROVIDER_CONFIG,
        "security": _PROVIDER_CONFIG,
        "cross_repo": _PROVIDER_CONFIG,
    }

    def _make_context(self, shared_prompt: str = "test prompt") -> ReviewContext:
        return ReviewContext(
            owner="owner",
            repo="repo",
            pr_number=1,
            head_sha="abc123",
            pr_title="Fix bug",
            diff_text="### file.py\n@@ -1 +1 @@\n-patch",
            changed_paths=["file.py"],
            shared_prompt=shared_prompt,
        )

    def _make_bug_report(self, file: str = "src/a.py", line: int = 10) -> BugReport:
        return BugReport(
            file=file,
            line=line,
            severity="major",
            description="Bug found",
            suggestion="Fix it",
        )

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_both_reviewers_receive_identical_prompt(
        self, mock_openai_like, mock_agent_cls
    ):
        """Task 2.1 RED: both A and B receive the same shared_prompt."""
        from src.reviewer.orchestrator import _run_bug_reviewers

        shared_prompt = "identical prompt for both reviewers"
        ctx = self._make_context(shared_prompt=shared_prompt)

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(return_value=MagicMock(content=json.dumps({"bugs": []})))

        await _run_bug_reviewers(ctx, self._ROLE_CONFIGS, supports_structured_output=True)

        # Verify both agents were created with the same instructions
        assert mock_agent_cls.call_count == 2
        calls = mock_agent_cls.call_args_list
        assert calls[0].kwargs["instructions"] == calls[1].kwargs["instructions"]

        # Verify both agents received the same shared prompt via arun
        arun_calls = mock_agent.arun.call_args_list
        assert len(arun_calls) == 2
        assert arun_calls[0][0][0] == shared_prompt
        assert arun_calls[1][0][0] == shared_prompt

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_reviewers_do_not_see_each_others_output(
        self, mock_openai_like, mock_agent_cls
    ):
        """Task 2.1 RED: reviewers are blind to each other's outputs."""
        from src.reviewer.orchestrator import _run_bug_reviewers

        ctx = self._make_context()

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(return_value=MagicMock(content=json.dumps({"bugs": []})))

        result_a, result_b = await _run_bug_reviewers(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True
        )

        # Results should be independent SpecialistBugOutput instances
        assert isinstance(result_a, SpecialistBugOutput)
        assert isinstance(result_b, SpecialistBugOutput)
        assert result_a.provider == "bug-reviewer-a"
        assert result_b.provider == "bug-reviewer-b"

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_agents_use_same_model_config(
        self, mock_openai_like, mock_agent_cls
    ):
        """Task 2.1 RED: both agents use the same provider_config."""
        from src.reviewer.orchestrator import _run_bug_reviewers

        ctx = self._make_context()

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(return_value=MagicMock(content=json.dumps({"bugs": []})))

        await _run_bug_reviewers(ctx, self._ROLE_CONFIGS, supports_structured_output=True)

        # Verify OpenAILike was called with the same config for both agents.
        assert mock_openai_like.call_count == 2
        calls = mock_openai_like.call_args_list
        assert calls[0].kwargs["id"] == calls[1].kwargs["id"] == "my-model"
        assert calls[0].kwargs["base_url"] == calls[1].kwargs["base_url"]
        assert calls[0].kwargs["api_key"] == calls[1].kwargs["api_key"]

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_no_github_token_or_posting_tools_in_agents(
        self, mock_openai_like, mock_agent_cls
    ):
        """Task 2.1 RED: agents must not have github_token or post_review_comments."""
        from src.reviewer.orchestrator import _run_bug_reviewers

        ctx = self._make_context()

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(return_value=MagicMock(content=json.dumps({"bugs": []})))

        await _run_bug_reviewers(ctx, self._ROLE_CONFIGS, supports_structured_output=True)

        for call in mock_agent_cls.call_args_list:
            assert "github_token" not in str(call)
            assert "post_review_comments" not in str(call)
            # Agents should have NO tools
            assert call.kwargs.get("tools") is None

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_parse_structured_output(self, mock_openai_like, mock_agent_cls):
        """Task 2.2 GREEN: parses structured output from both reviewers."""
        from src.reviewer.orchestrator import _run_bug_reviewers

        ctx = self._make_context()
        bug = self._make_bug_report()

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(return_value=MagicMock(
            content=json.dumps({"bugs": [bug.model_dump()]})
        ))

        result_a, result_b = await _run_bug_reviewers(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True
        )

        assert len(result_a.bugs) == 1
        assert result_a.bugs[0].file == bug.file
        assert result_a.bugs[0].line == bug.line
        assert len(result_b.bugs) == 1
        assert result_b.bugs[0].file == bug.file

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_parse_failure_returns_empty(
        self, mock_openai_like, mock_agent_cls
    ):
        """Task 2.2 GREEN: parse failure returns empty bugs with raw_content preserved."""
        from src.reviewer.orchestrator import _run_bug_reviewers

        ctx = self._make_context()

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        def side_effect(*args, **kwargs):
            # First call returns invalid JSON, second returns valid
            call_count = mock_agent.arun.call_count
            if call_count == 1:
                return MagicMock(content="not valid json")
            return MagicMock(content=json.dumps({"bugs": []}))

        mock_agent.arun = MagicMock(side_effect=side_effect)

        result_a, result_b = await _run_bug_reviewers(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True
        )

        assert len(result_a.bugs) == 0
        assert result_a.raw_content == "not valid json"
        assert len(result_b.bugs) == 0

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_parse_success_ignores_model_metadata(
        self, mock_openai_like, mock_agent_cls
    ):
        from src.reviewer.orchestrator import _run_bug_reviewers

        ctx = self._make_context()
        bug = self._make_bug_report()

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(return_value=MagicMock(
            content=json.dumps(
                {
                    "bugs": [bug.model_dump()],
                    "provider": "wrong-provider",
                    "parse_failed": True,
                }
            )
        ))

        result_a, result_b = await _run_bug_reviewers(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True
        )

        assert result_a.provider == "bug-reviewer-a"
        assert result_a.parse_failed is False
        assert len(result_a.bugs) == 1
        assert result_b.provider == "bug-reviewer-b"

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_partial_failure_keeps_surviving_output(
        self, mock_openai_like, mock_agent_cls
    ):
        """FAIL-001: if one reviewer fails, the surviving output is preserved."""
        from src.reviewer.orchestrator import _run_bug_reviewers

        ctx = self._make_context()
        bug = self._make_bug_report()

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        def side_effect(*args, **kwargs):
            call_count = mock_agent.arun.call_count
            if call_count == 1:
                raise RuntimeError("agent exploded")
            return MagicMock(content=json.dumps({"bugs": [bug.model_dump()]}))

        mock_agent.arun = MagicMock(side_effect=side_effect)

        result_a, result_b = await _run_bug_reviewers(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True
        )

        assert result_a.provider == "bug-reviewer-a"
        assert result_a.bugs == []
        assert result_a.parse_failed is True
        assert result_b.provider == "bug-reviewer-b"
        assert len(result_b.bugs) == 1
        assert result_b.bugs[0].file == bug.file

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_timeout_preserves_other_pass_output(
        self, mock_openai_like, mock_agent_cls
    ):
        """2.3: one bug pass timeout logs warning and preserves other pass output."""
        import asyncio
        from src.reviewer.orchestrator import _run_bug_reviewers

        ctx = self._make_context()
        bug = self._make_bug_report()

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        async def slow_run(*args, **kwargs):
            await asyncio.sleep(10)
            return MagicMock(content=json.dumps({"bugs": []}))

        def side_effect(*args, **kwargs):
            call_count = mock_agent.arun.call_count
            if call_count == 1:
                return slow_run()
            return MagicMock(content=json.dumps({"bugs": [bug.model_dump()]}))

        mock_agent.arun = MagicMock(side_effect=side_effect)

        with patch("src.reviewer.orchestrator.Config") as mock_cfg:
            mock_cfg.REVIEW_SPECIALIST_TIMEOUT_SECONDS = 0.1
            result_a, result_b = await _run_bug_reviewers(
                ctx, self._ROLE_CONFIGS, supports_structured_output=True
            )

        assert result_a.provider == "bug-reviewer-a"
        assert result_a.parse_failed is True
        assert result_a.bugs == []
        assert result_b.provider == "bug-reviewer-b"
        assert len(result_b.bugs) == 1
        assert result_b.bugs[0].file == bug.file

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_total_failure_returns_empty_outputs(
        self, mock_openai_like, mock_agent_cls
    ):
        """FAIL-001: if both reviewers fail, empty markers are returned."""
        from src.reviewer.orchestrator import _run_bug_reviewers

        ctx = self._make_context()

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_agent.arun = MagicMock(side_effect=RuntimeError("both exploded"))

        result_a, result_b = await _run_bug_reviewers(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True
        )

        assert result_a.provider == "bug-reviewer-a"
        assert result_a.bugs == []
        assert result_a.parse_failed is True
        assert result_b.provider == "bug-reviewer-b"
        assert result_b.bugs == []
        assert result_b.parse_failed is True

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_fenced_json_parses_successfully_and_preserves_raw_content(
        self, mock_openai_like, mock_agent_cls
    ):
        """Task 2.2 RED: markdown-fenced JSON is extracted; raw_content stays unchanged."""
        from src.reviewer.orchestrator import _run_bug_reviewers

        ctx = self._make_context()
        bug = self._make_bug_report()
        original_response = '```json\n{"bugs": [' + json.dumps(bug.model_dump()) + "]}\n```"

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        def side_effect(*args, **kwargs):
            call_count = mock_agent.arun.call_count
            if call_count == 1:
                return MagicMock(content=original_response)
            return MagicMock(content=json.dumps({"bugs": []}))

        mock_agent.arun = MagicMock(side_effect=side_effect)

        result_a, result_b = await _run_bug_reviewers(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True
        )

        assert len(result_a.bugs) == 1
        assert result_a.bugs[0].file == bug.file
        assert result_a.raw_content == original_response
        assert result_a.parse_failed is False
        assert len(result_b.bugs) == 0

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_prose_wrapped_json_parses_successfully_and_preserves_raw_content(
        self, mock_openai_like, mock_agent_cls
    ):
        """Task 2.3 RED: prose-wrapped JSON is extracted; raw_content stays unchanged."""
        from src.reviewer.orchestrator import _run_bug_reviewers

        ctx = self._make_context()
        bug = self._make_bug_report()
        original_response = (
            "Here is my analysis:\n\n"
            '```json\n{"bugs": [' + json.dumps(bug.model_dump()) + "]}\n```\n\n"
            "Let me know if you need anything else."
        )

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        def side_effect(*args, **kwargs):
            call_count = mock_agent.arun.call_count
            if call_count == 1:
                return MagicMock(content=original_response)
            return MagicMock(content=json.dumps({"bugs": []}))

        mock_agent.arun = MagicMock(side_effect=side_effect)

        result_a, result_b = await _run_bug_reviewers(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True
        )

        assert len(result_a.bugs) == 1
        assert result_a.bugs[0].file == bug.file
        assert result_a.raw_content == original_response
        assert result_a.parse_failed is False
        assert len(result_b.bugs) == 0

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_invalid_json_fails_gracefully_and_preserves_raw_content(
        self, mock_openai_like, mock_agent_cls
    ):
        """Task 2.4 RED: no valid JSON → parse failure with raw_content unchanged."""
        from src.reviewer.orchestrator import _run_bug_reviewers

        ctx = self._make_context()
        original_response = "This is just prose with no JSON at all."

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        def side_effect(*args, **kwargs):
            call_count = mock_agent.arun.call_count
            if call_count == 1:
                return MagicMock(content=original_response)
            return MagicMock(content=json.dumps({"bugs": []}))

        mock_agent.arun = MagicMock(side_effect=side_effect)

        result_a, result_b = await _run_bug_reviewers(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True
        )

        assert len(result_a.bugs) == 0
        assert result_a.raw_content == original_response
        assert result_a.parse_failed is True
        assert len(result_b.bugs) == 0

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_balanced_json_scan_without_fences(
        self, mock_openai_like, mock_agent_cls
    ):
        """Triangulation: bare JSON object embedded in prose (no fences)."""
        from src.reviewer.orchestrator import _run_bug_reviewers

        ctx = self._make_context()
        bug = self._make_bug_report()
        original_response = (
            "Here is the result: {"
            + json.dumps("bugs")
            + ": ["
            + json.dumps(bug.model_dump())
            + "]} thanks for reading."
        )

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        def side_effect(*args, **kwargs):
            call_count = mock_agent.arun.call_count
            if call_count == 1:
                return MagicMock(content=original_response)
            return MagicMock(content=json.dumps({"bugs": []}))

        mock_agent.arun = MagicMock(side_effect=side_effect)

        result_a, result_b = await _run_bug_reviewers(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True
        )

        assert len(result_a.bugs) == 1
        assert result_a.bugs[0].file == bug.file
        assert result_a.raw_content == original_response
        assert len(result_b.bugs) == 0

    @pytest.mark.anyio
    @patch("src.reviewer.orchestrator.Agent")
    @patch("src.reviewer.orchestrator.OpenAILike")
    async def test_multiple_fenced_blocks_skips_invalid_to_valid(
        self, mock_openai_like, mock_agent_cls
    ):
        """Triangulation: first fence is invalid JSON, second fence is valid."""
        from src.reviewer.orchestrator import _run_bug_reviewers

        ctx = self._make_context()
        bug = self._make_bug_report()
        original_response = (
            "```json\n{invalid json}\n```\n\n"
            '```json\n{"bugs": [' + json.dumps(bug.model_dump()) + "]}\n```"
        )

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        def side_effect(*args, **kwargs):
            call_count = mock_agent.arun.call_count
            if call_count == 1:
                return MagicMock(content=original_response)
            return MagicMock(content=json.dumps({"bugs": []}))

        mock_agent.arun = MagicMock(side_effect=side_effect)

        result_a, result_b = await _run_bug_reviewers(
            ctx, self._ROLE_CONFIGS, supports_structured_output=True
        )

        # Should skip invalid first fence and find valid second fence
        assert len(result_a.bugs) == 1
        assert result_a.bugs[0].file == bug.file
        assert result_a.raw_content == original_response
        assert len(result_b.bugs) == 0

    def test_extract_json_with_brace_inside_string(self):
        """Regression RED: prose-wrapped JSON with } inside a string value."""
        from src.reviewer.orchestrator import _extract_json_object_text

        raw = 'prefix {"desc": "uses } brace"} suffix'
        result = _extract_json_object_text(raw)
        assert result == '{"desc": "uses } brace"}'

    def test_extract_json_with_open_brace_inside_string(self):
        """Triangulation: { inside a string value must not increase depth."""
        from src.reviewer.orchestrator import _extract_json_object_text

        raw = 'prefix {"desc": "uses { brace"} suffix'
        result = _extract_json_object_text(raw)
        assert result == '{"desc": "uses { brace"}'

    def test_extract_json_with_both_braces_inside_string(self):
        """Triangulation: both { and } inside string values."""
        from src.reviewer.orchestrator import _extract_json_object_text

        raw = 'prefix {"a": "{", "b": "}"} suffix'
        result = _extract_json_object_text(raw)
        assert result == '{"a": "{", "b": "}"}'

    def test_extract_json_with_escaped_quote_inside_string(self):
        """Triangulation: escaped quotes must not terminate string early."""
        from src.reviewer.orchestrator import _extract_json_object_text

        raw = 'prefix {"desc": "say \\"hello\\" } end"} suffix'
        result = _extract_json_object_text(raw)
        assert result == '{"desc": "say \\"hello\\" } end"}'

    def test_extract_json_with_escaped_backslash_before_quote(self):
        """Triangulation: \\ before quote means quote terminates string."""
        from src.reviewer.orchestrator import _extract_json_object_text

        raw = 'prefix {"path": "C:\\\\dir", "ok": true} suffix'
        result = _extract_json_object_text(raw)
        assert result == '{"path": "C:\\\\dir", "ok": true}'

    def test_extract_json_multiple_objects_braces_in_strings(self):
        """Triangulation: first object has braces in strings; second is plain."""
        from src.reviewer.orchestrator import _extract_json_object_text

        raw = 'prefix {"a": "}x{"} middle {"b": 2} suffix'
        result = _extract_json_object_text(raw)
        assert result == '{"a": "}x{"}'

    def test_parse_success_logs_specialist_output(self, caplog):
        """Observability: successful bug parse logs preview and counts at INFO."""
        import logging

        from src.reviewer.orchestrator import _parse_specialist_bug_output

        ctx = self._make_context()
        raw = json.dumps(
            {
                "bugs": [
                    {
                        "file": "a.py",
                        "line": 1,
                        "severity": "major",
                        "description": "d",
                        "suggestion": "s",
                    }
                ]
            }
        )
        with caplog.at_level(logging.INFO):
            result = _parse_specialist_bug_output(raw, "bug-reviewer-a", ctx)
        assert result.parse_failed is False
        logs = [r for r in caplog.records if "bug-reviewer-a" in r.getMessage()]
        assert len(logs) == 1
        msg = logs[0].getMessage()
        assert "bug_count" in msg
        assert "1" in msg
        assert "parse_failed" in msg

    def test_parse_empty_bug_json_logs_specialist_output(self, caplog):
        """Observability: empty bugs JSON logs zero count to diagnose model drift."""
        import logging

        from src.reviewer.orchestrator import _parse_specialist_bug_output

        ctx = self._make_context()
        raw = json.dumps({"bugs": []})
        with caplog.at_level(logging.INFO):
            result = _parse_specialist_bug_output(raw, "bug-reviewer-b", ctx)
        assert result.parse_failed is False
        logs = [r for r in caplog.records if "bug-reviewer-b" in r.getMessage()]
        assert len(logs) == 1
        msg = logs[0].getMessage()
        assert "bug_count" in msg
        assert "0" in msg
        assert "top_level_keys" in msg

    def test_parse_failure_logs_specialist_output(self, caplog):
        """Observability: parse failure logs preview with parse_failed=True."""
        import logging

        from src.reviewer.orchestrator import _parse_specialist_bug_output

        ctx = self._make_context()
        raw = "not valid json"
        with caplog.at_level(logging.INFO):
            result = _parse_specialist_bug_output(raw, "bug-reviewer-a", ctx)
        assert result.parse_failed is True
        logs = [r for r in caplog.records if "bug-reviewer-a" in r.getMessage()]
        assert len(logs) == 1
        msg = logs[0].getMessage()
        assert "parse_failed" in msg

    def test_parse_misshaped_key_logs_top_level_keys_on_success(self, caplog):
        """Observability: mis-shaped key (findings instead of bugs) logs keys so drift is visible.

        Pydantic v2 ignores extra fields by default, so parsing succeeds but
        bug_count is zero.  The logged top_level_keys reveals the model used
        'findings' instead of 'bugs'.
        """
        import logging

        from src.reviewer.orchestrator import _parse_specialist_bug_output

        ctx = self._make_context()
        raw = json.dumps({"findings": [{"desc": "x"}]})
        with caplog.at_level(logging.INFO):
            result = _parse_specialist_bug_output(raw, "bug-reviewer-a", ctx)
        assert result.parse_failed is False
        assert len(result.bugs) == 0
        logs = [r for r in caplog.records if "bug-reviewer-a" in r.getMessage()]
        assert len(logs) == 1
        msg = logs[0].getMessage()
        assert "findings" in msg
        assert "bug_count" in msg
        assert "0" in msg
