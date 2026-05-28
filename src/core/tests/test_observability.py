"""Tests for src/core/observability.py — Opik setup and prompt registry."""

import sys
import pytest
from unittest.mock import MagicMock, patch

import src.core.observability as obs_module
from src.core.config import Config


# ---------------------------------------------------------------------------
# Auto-reset module-level state before each test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_observability_state(monkeypatch):
    """Reset module-level state before each test."""
    monkeypatch.setattr(obs_module, "_configured", False)
    if hasattr(obs_module, "_prompt_cache"):
        obs_module._prompt_cache.clear()
    else:
        monkeypatch.setattr(obs_module, "_cached_prompt", None)
    yield
    if hasattr(obs_module, "_prompt_cache"):
        obs_module._prompt_cache.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_opik_mock():
    """Return a minimal opik mock suitable for patching sys.modules."""
    mock_opik = MagicMock()
    return mock_opik


def _make_agno_mock():
    """Return a minimal openinference.instrumentation.agno mock."""
    mock_agno = MagicMock()
    return mock_agno


# ---------------------------------------------------------------------------
# TestConfigureOpikNoOp
# ---------------------------------------------------------------------------


class TestConfigureOpikNoOp:
    def test_returns_without_importing_opik_when_key_is_empty(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "")

        # Remove opik from sys.modules so we can detect an accidental import.
        sys.modules.pop("opik", None)

        obs_module.configure_opik()

        assert "opik" not in sys.modules

    def test_does_not_raise_when_key_is_empty(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "")
        obs_module.configure_opik()  # must not raise

    def test_sets_configured_flag_when_key_is_empty(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "")
        obs_module.configure_opik()
        assert obs_module._configured is True


# ---------------------------------------------------------------------------
# TestConfigureOpikActive
# ---------------------------------------------------------------------------


class TestConfigureOpikActive:
    def test_calls_opik_configure_with_api_key(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")
        monkeypatch.setattr(Config, "OPIK_PROJECT_NAME", "pr-reviewer")
        monkeypatch.setattr(Config, "OPIK_WORKSPACE", "")

        mock_opik = _make_opik_mock()
        mock_agno = _make_agno_mock()

        with patch.dict(
            "sys.modules",
            {
                "opik": mock_opik,
                "openinference.instrumentation.agno": mock_agno,
            },
        ):
            obs_module.configure_opik()

        mock_opik.configure.assert_called_once()
        call_kwargs = mock_opik.configure.call_args.kwargs
        assert call_kwargs["api_key"] == "test-key"

    def test_does_not_include_workspace_when_empty(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")
        monkeypatch.setattr(Config, "OPIK_PROJECT_NAME", "pr-reviewer")
        monkeypatch.setattr(Config, "OPIK_WORKSPACE", "")

        mock_opik = _make_opik_mock()
        mock_agno = _make_agno_mock()

        with patch.dict(
            "sys.modules",
            {
                "opik": mock_opik,
                "openinference.instrumentation.agno": mock_agno,
            },
        ):
            obs_module.configure_opik()

        call_kwargs = mock_opik.configure.call_args.kwargs
        assert "workspace" not in call_kwargs

    def test_includes_workspace_when_non_empty(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")
        monkeypatch.setattr(Config, "OPIK_PROJECT_NAME", "pr-reviewer")
        monkeypatch.setattr(Config, "OPIK_WORKSPACE", "my-team")

        mock_opik = _make_opik_mock()
        mock_agno = _make_agno_mock()

        with patch.dict(
            "sys.modules",
            {
                "opik": mock_opik,
                "openinference.instrumentation.agno": mock_agno,
            },
        ):
            obs_module.configure_opik()

        call_kwargs = mock_opik.configure.call_args.kwargs
        assert call_kwargs["workspace"] == "my-team"

    def test_calls_agno_instrumentor_instrument(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")
        monkeypatch.setattr(Config, "OPIK_PROJECT_NAME", "pr-reviewer")
        monkeypatch.setattr(Config, "OPIK_WORKSPACE", "")

        mock_opik = _make_opik_mock()
        mock_agno = _make_agno_mock()

        with patch.dict(
            "sys.modules",
            {
                "opik": mock_opik,
                "openinference.instrumentation.agno": mock_agno,
            },
        ):
            obs_module.configure_opik()

        mock_agno.AgnoInstrumentor.return_value.instrument.assert_called_once()

    def test_sets_configured_flag_when_key_is_set(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")
        monkeypatch.setattr(Config, "OPIK_WORKSPACE", "")

        mock_opik = _make_opik_mock()
        mock_agno = _make_agno_mock()

        with patch.dict(
            "sys.modules",
            {
                "opik": mock_opik,
                "openinference.instrumentation.agno": mock_agno,
            },
        ):
            obs_module.configure_opik()

        assert obs_module._configured is True


# ---------------------------------------------------------------------------
# TestConfigureOpikIdempotent
# ---------------------------------------------------------------------------


class TestConfigureOpikIdempotent:
    def test_opik_configure_called_exactly_once_on_double_call(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")
        monkeypatch.setattr(Config, "OPIK_WORKSPACE", "")

        mock_opik = _make_opik_mock()
        mock_agno = _make_agno_mock()

        with patch.dict(
            "sys.modules",
            {
                "opik": mock_opik,
                "openinference.instrumentation.agno": mock_agno,
            },
        ):
            obs_module.configure_opik()
            obs_module.configure_opik()

        mock_opik.configure.assert_called_once()

    def test_agno_instrumentor_called_exactly_once_on_double_call(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")
        monkeypatch.setattr(Config, "OPIK_WORKSPACE", "")

        mock_opik = _make_opik_mock()
        mock_agno = _make_agno_mock()

        with patch.dict(
            "sys.modules",
            {
                "opik": mock_opik,
                "openinference.instrumentation.agno": mock_agno,
            },
        ):
            obs_module.configure_opik()
            obs_module.configure_opik()

        mock_agno.AgnoInstrumentor.return_value.instrument.assert_called_once()

    def test_no_exception_on_double_call(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")
        monkeypatch.setattr(Config, "OPIK_WORKSPACE", "")

        mock_opik = _make_opik_mock()
        mock_agno = _make_agno_mock()

        with patch.dict(
            "sys.modules",
            {
                "opik": mock_opik,
                "openinference.instrumentation.agno": mock_agno,
            },
        ):
            obs_module.configure_opik()
            obs_module.configure_opik()  # must not raise


class TestGenericPromptRegistry:
    def test_active_prompt_names_are_exactly_multi_agent_prompts(self):
        assert obs_module.ACTIVE_PROMPT_NAMES == (
            "bug_reviewer_instructions",
            "security_reviewer_instructions",
            "cross_repo_impact_reviewer_instructions",
            "pr_review_prompt",
        )

    def test_get_prompt_fetches_arbitrary_name_from_opik(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")
        mock_opik = _make_opik_mock()
        mock_prompt_obj = MagicMock(spec=["format"])
        mock_prompt_obj.format.return_value = "Bug prompt from Opik"
        mock_opik.Opik.return_value.get_prompt.return_value = mock_prompt_obj

        with patch.dict("sys.modules", {"opik": mock_opik}):
            result = obs_module.get_prompt("bug_reviewer_instructions")

        assert result == "Bug prompt from Opik"
        mock_opik.Opik.return_value.get_prompt.assert_called_once_with(
            name="bug_reviewer_instructions"
        )

    def test_get_prompt_caches_raw_opik_template_without_rendering_variables(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")
        mock_opik = _make_opik_mock()
        mock_prompt_obj = MagicMock()
        mock_prompt_obj._template = "Title={pr_title}; Diff={diff_text}"
        mock_prompt_obj.format.side_effect = KeyError("pr_title")
        mock_opik.Opik.return_value.get_prompt.return_value = mock_prompt_obj

        with patch.dict("sys.modules", {"opik": mock_opik}):
            result = obs_module.render_prompt(
                "pr_review_prompt", pr_title="Safe title", diff_text="Safe diff"
            )

        assert result == "Title=Safe title; Diff=Safe diff"
        mock_prompt_obj.format.assert_not_called()

    def test_prompt_cache_is_isolated_per_name(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")
        mock_opik = _make_opik_mock()

        def get_prompt(name):
            prompt_obj = MagicMock()
            prompt_obj.format.return_value = f"Opik {name}"
            return prompt_obj

        mock_opik.Opik.return_value.get_prompt.side_effect = get_prompt

        with patch.dict("sys.modules", {"opik": mock_opik}):
            bug = obs_module.get_prompt("bug_reviewer_instructions")
            security = obs_module.get_prompt("security_reviewer_instructions")
            bug_again = obs_module.get_prompt("bug_reviewer_instructions")

        assert bug == "Opik bug_reviewer_instructions"
        assert security == "Opik security_reviewer_instructions"
        assert bug_again == bug
        assert mock_opik.Opik.return_value.get_prompt.call_count == 2

    def test_get_prompt_falls_back_to_matching_file_on_opik_failure(
        self, monkeypatch, tmp_path, caplog
    ):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "secret-token")
        monkeypatch.setattr(obs_module, "_PROJECT_ROOT", tmp_path)
        prompt_file = tmp_path / "prompts" / "security_reviewer_instructions.txt"
        prompt_file.parent.mkdir(parents=True)
        prompt_file.write_text("Security fallback", encoding="utf-8")
        mock_opik = _make_opik_mock()
        mock_opik.Opik.return_value.get_prompt.side_effect = RuntimeError("boom secret-token")

        with patch.dict("sys.modules", {"opik": mock_opik}):
            with caplog.at_level("WARNING", logger="src.core.observability"):
                result = obs_module.get_prompt("security_reviewer_instructions")

        assert result == "Security fallback"
        log_text = "\n".join(caplog.messages)
        assert "security_reviewer_instructions" in log_text
        assert "secret-token" not in log_text

    def test_get_prompt_reads_file_without_importing_opik_when_key_empty(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "")
        monkeypatch.setattr(obs_module, "_PROJECT_ROOT", tmp_path)
        prompt_file = tmp_path / "prompts" / "bug_reviewer_instructions.txt"
        prompt_file.parent.mkdir(parents=True)
        prompt_file.write_text("Bug fallback", encoding="utf-8")
        sys.modules.pop("opik", None)

        result = obs_module.get_prompt("bug_reviewer_instructions")

        assert result == "Bug fallback"
        assert "opik" not in sys.modules

    def test_warm_prompt_cache_loads_each_requested_prompt(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "")
        monkeypatch.setattr(obs_module, "_PROJECT_ROOT", tmp_path)
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir(parents=True)
        for name in ("bug_reviewer_instructions", "security_reviewer_instructions"):
            (prompts_dir / f"{name}.txt").write_text(f"Fallback {name}", encoding="utf-8")

        obs_module.warm_prompt_cache(
            ("bug_reviewer_instructions", "security_reviewer_instructions")
        )

        assert obs_module._prompt_cache == {
            "bug_reviewer_instructions": "Fallback bug_reviewer_instructions",
            "security_reviewer_instructions": "Fallback security_reviewer_instructions",
        }

    def test_render_prompt_uses_only_registered_variables(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "")
        monkeypatch.setattr(obs_module, "_PROJECT_ROOT", tmp_path)
        prompt_file = tmp_path / "prompts" / "pr_review_prompt.txt"
        prompt_file.parent.mkdir(parents=True)
        prompt_file.write_text("Title={pr_title}; Diff={diff_text}", encoding="utf-8")

        result = obs_module.render_prompt(
            "pr_review_prompt",
            pr_title="Safe title",
            diff_text="Safe diff",
            ignored="nope",
        )

        assert result == "Title=Safe title; Diff=Safe diff"

    def test_render_prompt_preserves_literal_json_braces(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "")
        monkeypatch.setattr(obs_module, "_PROJECT_ROOT", tmp_path)
        prompt_file = tmp_path / "prompts" / "pr_review_prompt.txt"
        prompt_file.parent.mkdir(parents=True)
        prompt_file.write_text(
            'Return JSON like {"summary": "x"}. Title={pr_title}; Diff={diff_text}',
            encoding="utf-8",
        )

        result = obs_module.render_prompt(
            "pr_review_prompt",
            pr_title="Safe title",
            diff_text="Safe diff",
        )

        assert result == 'Return JSON like {"summary": "x"}. Title=Safe title; Diff=Safe diff'
