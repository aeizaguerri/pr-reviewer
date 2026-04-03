"""Unit tests: L5 — Diff truncation in fetch_pr_data."""

import logging
from unittest.mock import MagicMock, patch


import src.core.config as cfg_module
from src.reviewer.tools import fetch_pr_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_pr(patch_text: str, title: str = "Test PR", sha: str = "deadbeef"):
    """Build a minimal PyGithub mock PR with a single file whose patch is patch_text."""
    mock_file = MagicMock()
    mock_file.filename = "src/main.py"
    mock_file.patch = patch_text

    mock_pr = MagicMock()
    mock_pr.head.sha = sha
    mock_pr.title = title
    mock_pr.get_files.return_value = [mock_file]
    return mock_pr


# ---------------------------------------------------------------------------
# Tests — SC-L5-1 through SC-L5-4
# ---------------------------------------------------------------------------


class TestDiffTruncation:
    @patch("src.reviewer.tools.Github")
    def test_short_diff_is_not_truncated(self, mock_github_cls, monkeypatch):
        """SC-L5-1: A diff within MAX_DIFF_CHARS limit is returned unchanged."""
        monkeypatch.setattr(cfg_module.Config, "MAX_DIFF_CHARS", 1000)

        patch_text = "x" * 500
        mock_github_cls.return_value.get_repo.return_value.get_pull.return_value = (
            _make_mock_pr(patch_text)
        )

        diff_text, _, _ = fetch_pr_data("owner", "repo", 1, github_token="tok")

        assert "[TRUNCATED" not in diff_text
        # The full patch appears in the diff (inside the "### filename\n{patch}" block)
        assert patch_text in diff_text

    @patch("src.reviewer.tools.Github")
    def test_long_diff_is_truncated(self, mock_github_cls, monkeypatch):
        """SC-L5-2: A diff exceeding MAX_DIFF_CHARS is cut and ends with [TRUNCATED]."""
        limit = 500
        monkeypatch.setattr(cfg_module.Config, "MAX_DIFF_CHARS", limit)

        patch_text = "y" * 10_000
        mock_github_cls.return_value.get_repo.return_value.get_pull.return_value = (
            _make_mock_pr(patch_text)
        )

        diff_text, _, _ = fetch_pr_data("owner", "repo", 1, github_token="tok")

        assert diff_text.endswith("[TRUNCATED — diff exceeded size limit]")
        # Content up to the limit + marker — must not exceed limit + marker length
        marker = "\n\n[TRUNCATED — diff exceeded size limit]"
        assert len(diff_text) == limit + len(marker)

    @patch("src.reviewer.tools.Github")
    def test_truncation_emits_warning(self, mock_github_cls, monkeypatch, caplog):
        """SC-L5-3: A warning is logged when the diff is truncated."""
        limit = 200
        monkeypatch.setattr(cfg_module.Config, "MAX_DIFF_CHARS", limit)

        patch_text = "z" * 5_000
        mock_github_cls.return_value.get_repo.return_value.get_pull.return_value = (
            _make_mock_pr(patch_text)
        )

        with caplog.at_level(logging.WARNING, logger="src.reviewer.tools"):
            fetch_pr_data("owner", "repo", 99, github_token="tok")

        assert len(caplog.records) >= 1
        warning_text = " ".join(caplog.messages)
        # The warning must mention the exact original char count of the assembled diff
        # assembled diff = "### src/main.py\n" (16 chars) + patch_text (5000 chars) = 5016
        original_diff_len = len("### src/main.py\n") + len(patch_text)
        assert str(original_diff_len) in warning_text

    @patch("src.reviewer.tools.Github")
    def test_max_diff_chars_configurable(self, mock_github_cls, monkeypatch):
        """SC-L5-4: A custom MAX_DIFF_CHARS value controls the truncation point."""
        custom_limit = 50
        monkeypatch.setattr(cfg_module.Config, "MAX_DIFF_CHARS", custom_limit)

        patch_text = "a" * 1_000
        mock_github_cls.return_value.get_repo.return_value.get_pull.return_value = (
            _make_mock_pr(patch_text)
        )

        diff_text, _, _ = fetch_pr_data("owner", "repo", 1, github_token="tok")

        marker = "\n\n[TRUNCATED — diff exceeded size limit]"
        assert len(diff_text) == custom_limit + len(marker)
        assert diff_text.endswith("[TRUNCATED — diff exceeded size limit]")

    @patch("src.reviewer.tools.Github")
    def test_diff_exactly_at_limit_is_not_truncated(self, mock_github_cls, monkeypatch):
        """Edge case: diff length == MAX_DIFF_CHARS → NOT truncated."""
        limit = 100
        monkeypatch.setattr(cfg_module.Config, "MAX_DIFF_CHARS", limit)

        # Build a patch whose assembled diff_text is exactly `limit` chars.
        # "### src/main.py\n" is 16 chars; so patch needs limit - 16 chars.
        patch_text = "b" * (limit - len("### src/main.py\n"))
        mock_github_cls.return_value.get_repo.return_value.get_pull.return_value = (
            _make_mock_pr(patch_text)
        )

        diff_text, _, _ = fetch_pr_data("owner", "repo", 1, github_token="tok")

        assert "[TRUNCATED" not in diff_text
        assert len(diff_text) == limit
