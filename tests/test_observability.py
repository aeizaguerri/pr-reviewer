"""Tests for src/core/observability.py — configure_opik() and get_reviewer_prompt()."""

import sys
import pytest
from unittest.mock import MagicMock, patch, call

import src.core.observability as obs_module
from src.core.config import Config


# ---------------------------------------------------------------------------
# Auto-reset module-level state before each test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_observability_state(monkeypatch):
    """Reset module-level state before each test."""
    monkeypatch.setattr(obs_module, "_configured", False)
    monkeypatch.setattr(obs_module, "_cached_prompt", None)
    yield


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


# ---------------------------------------------------------------------------
# TestGetReviewerPromptFromOpik
# ---------------------------------------------------------------------------


class TestGetReviewerPromptFromOpik:
    def test_returns_prompt_from_opik_when_key_is_set(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")

        mock_opik = _make_opik_mock()
        mock_prompt_obj = MagicMock()
        mock_prompt_obj.format.return_value = "Opik prompt text"
        mock_opik.Opik.return_value.get_prompt.return_value = mock_prompt_obj

        with patch.dict("sys.modules", {"opik": mock_opik}):
            result = obs_module.get_reviewer_prompt()

        assert result == "Opik prompt text"

    def test_caches_result_on_second_call(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")

        mock_opik = _make_opik_mock()
        mock_prompt_obj = MagicMock()
        mock_prompt_obj.format.return_value = "Opik prompt text"
        mock_opik.Opik.return_value.get_prompt.return_value = mock_prompt_obj

        with patch.dict("sys.modules", {"opik": mock_opik}):
            first = obs_module.get_reviewer_prompt()
            second = obs_module.get_reviewer_prompt()

        assert first == second
        # get_prompt should have been called only once — second call hits cache
        mock_opik.Opik.return_value.get_prompt.assert_called_once()

    def test_cached_prompt_module_variable_is_set(self, monkeypatch):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")

        mock_opik = _make_opik_mock()
        mock_prompt_obj = MagicMock()
        mock_prompt_obj.format.return_value = "Opik prompt text"
        mock_opik.Opik.return_value.get_prompt.return_value = mock_prompt_obj

        with patch.dict("sys.modules", {"opik": mock_opik}):
            obs_module.get_reviewer_prompt()

        assert obs_module._cached_prompt == "Opik prompt text"


# ---------------------------------------------------------------------------
# TestGetReviewerPromptFallback
# ---------------------------------------------------------------------------


class TestGetReviewerPromptFallback:
    def test_falls_back_to_file_when_opik_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")
        monkeypatch.setattr(obs_module, "_PROJECT_ROOT", tmp_path)

        prompt_file = tmp_path / "prompts" / "reviewer_instructions.txt"
        prompt_file.parent.mkdir(parents=True)
        prompt_file.write_text("Fallback prompt from file", encoding="utf-8")

        mock_opik = _make_opik_mock()
        mock_opik.Opik.return_value.get_prompt.side_effect = RuntimeError("unreachable")

        with patch.dict("sys.modules", {"opik": mock_opik}):
            result = obs_module.get_reviewer_prompt()

        assert result == "Fallback prompt from file"

    def test_logs_warning_when_opik_fetch_fails(self, monkeypatch, tmp_path, caplog):
        import logging

        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")
        monkeypatch.setattr(obs_module, "_PROJECT_ROOT", tmp_path)

        prompt_file = tmp_path / "prompts" / "reviewer_instructions.txt"
        prompt_file.parent.mkdir(parents=True)
        prompt_file.write_text("Fallback prompt from file", encoding="utf-8")

        mock_opik = _make_opik_mock()
        mock_opik.Opik.return_value.get_prompt.side_effect = ConnectionError("timeout")

        with patch.dict("sys.modules", {"opik": mock_opik}):
            with caplog.at_level(logging.WARNING, logger="src.core.observability"):
                obs_module.get_reviewer_prompt()

        assert any(
            "warning" in r.levelname.lower() or r.levelno >= logging.WARNING for r in caplog.records
        )

    def test_fallback_result_is_cached(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "test-key")
        monkeypatch.setattr(obs_module, "_PROJECT_ROOT", tmp_path)

        prompt_file = tmp_path / "prompts" / "reviewer_instructions.txt"
        prompt_file.parent.mkdir(parents=True)
        prompt_file.write_text("Fallback prompt from file", encoding="utf-8")

        mock_opik = _make_opik_mock()
        mock_opik.Opik.return_value.get_prompt.side_effect = RuntimeError("unreachable")

        with patch.dict("sys.modules", {"opik": mock_opik}):
            obs_module.get_reviewer_prompt()
            obs_module.get_reviewer_prompt()

        # get_prompt should have been called once — second call hits cache
        mock_opik.Opik.return_value.get_prompt.assert_called_once()


# ---------------------------------------------------------------------------
# TestGetReviewerPromptNoApiKey
# ---------------------------------------------------------------------------


class TestGetReviewerPromptNoApiKey:
    def test_reads_file_directly_when_key_is_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "")
        monkeypatch.setattr(obs_module, "_PROJECT_ROOT", tmp_path)

        prompt_file = tmp_path / "prompts" / "reviewer_instructions.txt"
        prompt_file.parent.mkdir(parents=True)
        prompt_file.write_text("File-based prompt text", encoding="utf-8")

        sys.modules.pop("opik", None)

        result = obs_module.get_reviewer_prompt()

        assert result == "File-based prompt text"

    def test_does_not_import_opik_when_key_is_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "")
        monkeypatch.setattr(obs_module, "_PROJECT_ROOT", tmp_path)

        prompt_file = tmp_path / "prompts" / "reviewer_instructions.txt"
        prompt_file.parent.mkdir(parents=True)
        prompt_file.write_text("File-based prompt text", encoding="utf-8")

        sys.modules.pop("opik", None)

        obs_module.get_reviewer_prompt()

        assert "opik" not in sys.modules

    def test_caches_file_result(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Config, "OPIK_API_KEY", "")
        monkeypatch.setattr(obs_module, "_PROJECT_ROOT", tmp_path)

        prompt_file = tmp_path / "prompts" / "reviewer_instructions.txt"
        prompt_file.parent.mkdir(parents=True)
        prompt_file.write_text("File-based prompt text", encoding="utf-8")

        obs_module.get_reviewer_prompt()
        assert obs_module._cached_prompt == "File-based prompt text"

        # Mutate the file — second call must still return the cached value
        prompt_file.write_text("Updated content", encoding="utf-8")
        result = obs_module.get_reviewer_prompt()
        assert result == "File-based prompt text"
