"""Tests for src.core.logging_config — REQ-LOG-CONFIG through REQ-LOG-DISABLE-EXISTING."""

import logging
import logging.config
import warnings

import pytest

import src.core.logging_config as lc_module
from src.core.logging_config import configure_logging


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_configured_flag():
    """Reset the module-level _configured flag before each test.

    configure_logging() is idempotent — without this reset every test after
    the first would be a no-op, making assertions meaningless.
    """
    original = lc_module._configured
    lc_module._configured = False
    yield
    lc_module._configured = original


@pytest.fixture(autouse=True)
def clean_loggers():
    """Remove handlers added by configure_logging() after each test.

    dictConfig replaces existing handlers but we still want a clean slate
    so that captured-output assertions don't bleed across tests. We also
    restore propagate=True so that pytest's caplog fixture continues to
    work in other test modules after our tests run.
    """
    yield
    # Remove all handlers from root and known app loggers; restore defaults.
    for name in ("", "src", "backend", *lc_module._THIRD_PARTY_LOGGERS):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.setLevel(logging.NOTSET)
        if name != "":
            # Restore propagation so pytest caplog works in other test modules.
            lg.propagate = True


# ---------------------------------------------------------------------------
# 6.1 — REQ-LOG-CONFIG: module importable
# ---------------------------------------------------------------------------


class TestImportable:
    def test_import_succeeds(self):
        """configure_logging is importable without errors."""
        # If this file runs at all, the import at the top already succeeded.
        assert callable(configure_logging)


# ---------------------------------------------------------------------------
# 6.2 — REQ-LOG-APP / REQ-LOG-HANDLER: app loggers emit to stdout, propagate=False
# ---------------------------------------------------------------------------


class TestAppLoggerEmitsToStdout:
    def test_debug_message_goes_to_stdout(self, monkeypatch, capsys):
        """configure_logging(DEBUG) → src.* debug messages appear on stdout."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        configure_logging("DEBUG")

        logging.getLogger("src.test_module").debug("hello stdout")

        captured = capsys.readouterr()
        assert "hello stdout" in captured.out
        assert captured.err == ""

    def test_propagate_false_prevents_duplicate(self, monkeypatch):
        """src logger has propagate=False so root does not re-emit the record."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        configure_logging("DEBUG")

        src_logger = logging.getLogger("src")
        root_logger = logging.root

        assert src_logger.propagate is False
        # Root handler count should be 1 (the console handler we set), not 2.
        assert len(root_logger.handlers) == 1

    def test_format_contains_required_fields(self, monkeypatch, capsys):
        """Formatted output includes timestamp, level, logger name, and message."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        configure_logging("INFO")

        logging.getLogger("src.format_test").info("check-format")

        out = capsys.readouterr().out
        # Timestamp: starts with a digit (year)
        assert any(char.isdigit() for char in out.split()[0])
        assert "[INFO]" in out
        assert "src.format_test" in out
        assert "check-format" in out


# ---------------------------------------------------------------------------
# 6.3 — REQ-LOG-LEVEL: default is INFO
# ---------------------------------------------------------------------------


class TestDefaultLevel:
    def test_unset_env_var_defaults_to_info(self, monkeypatch):
        """When LOG_LEVEL env var is not set, effective level is INFO."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        # Patch Config.LOG_LEVEL to simulate missing env var
        import src.core.config as cfg_module

        monkeypatch.setattr(cfg_module.Config, "LOG_LEVEL", "INFO")

        configure_logging()

        src_logger = logging.getLogger("src")
        assert src_logger.level == logging.INFO

    def test_env_var_overrides_default(self, monkeypatch):
        """LOG_LEVEL=DEBUG env var → src.* loggers get DEBUG level."""
        import src.core.config as cfg_module

        monkeypatch.setattr(cfg_module.Config, "LOG_LEVEL", "DEBUG")

        configure_logging()

        src_logger = logging.getLogger("src")
        assert src_logger.level == logging.DEBUG


# ---------------------------------------------------------------------------
# 6.4 — REQ-LOG-LEVEL: invalid value falls back safely
# ---------------------------------------------------------------------------


class TestInvalidLevel:
    def test_invalid_level_does_not_raise(self, monkeypatch):
        """Invalid LOG_LEVEL=VERBOSE → no exception, falls back to INFO."""
        import src.core.config as cfg_module

        monkeypatch.setattr(cfg_module.Config, "LOG_LEVEL", "VERBOSE")

        # Should not raise
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            configure_logging()

        assert lc_module._configured is True

    def test_invalid_level_emits_warning(self, monkeypatch):
        """Invalid LOG_LEVEL → warnings.warn is called with a descriptive message."""
        import src.core.config as cfg_module

        monkeypatch.setattr(cfg_module.Config, "LOG_LEVEL", "BADLEVEL")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            configure_logging()

        assert len(caught) == 1
        assert "BADLEVEL" in str(caught[0].message)

    def test_invalid_level_falls_back_to_info(self, monkeypatch):
        """Invalid LOG_LEVEL → effective level is INFO (safe default)."""
        import src.core.config as cfg_module

        monkeypatch.setattr(cfg_module.Config, "LOG_LEVEL", "NONSENSE")

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            configure_logging()

        src_logger = logging.getLogger("src")
        assert src_logger.level == logging.INFO


# ---------------------------------------------------------------------------
# 6.5 — REQ-LOG-THIRDPARTY: third-party debug suppressed
# ---------------------------------------------------------------------------


class TestThirdPartyLoggers:
    def test_httpx_debug_suppressed(self, monkeypatch, capsys):
        """LOG_LEVEL=DEBUG → httpx debug messages are NOT emitted."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        configure_logging("DEBUG")

        httpx_logger = logging.getLogger("httpx")
        # isEnabledFor respects the logger's own level
        assert not httpx_logger.isEnabledFor(logging.DEBUG)

    def test_httpx_warning_visible(self, monkeypatch, capsys):
        """Third-party loggers still emit at WARNING level."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        configure_logging("DEBUG")

        httpx_logger = logging.getLogger("httpx")
        assert httpx_logger.isEnabledFor(logging.WARNING)

    def test_all_third_party_pinned_to_warning(self, monkeypatch):
        """All 7 third-party loggers are pinned at WARNING with propagate=False."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        configure_logging("DEBUG")

        for name in lc_module._THIRD_PARTY_LOGGERS:
            lg = logging.getLogger(name)
            assert lg.level == logging.WARNING, f"{name} should be WARNING"
            assert lg.propagate is False, f"{name} should have propagate=False"


# ---------------------------------------------------------------------------
# 6.6 — REQ-LOG-DISABLE-EXISTING: pre-existing loggers not silenced
# ---------------------------------------------------------------------------


class TestDisableExistingLoggers:
    def test_preexisting_logger_still_emits(self, monkeypatch, capsys):
        """A logger created BEFORE configure_logging still works afterwards."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        # Create logger BEFORE calling configure_logging (simulates import-time)
        preexisting = logging.getLogger("src.preexisting_test")

        configure_logging("DEBUG")

        preexisting.debug("pre-existing-message")
        out = capsys.readouterr().out
        assert "pre-existing-message" in out


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_second_call_is_noop(self, monkeypatch):
        """Calling configure_logging twice does not add duplicate handlers."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        configure_logging("INFO")
        handler_count_after_first = len(logging.getLogger("src").handlers)

        # Reset the flag manually to simulate a second call reaching the gate
        # NOTE: we do NOT reset — second call should hit the early return.
        configure_logging("DEBUG")

        handler_count_after_second = len(logging.getLogger("src").handlers)
        assert handler_count_after_first == handler_count_after_second
