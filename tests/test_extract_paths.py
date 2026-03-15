"""D.2 — Unit tests for _extract_changed_paths() in src/reviewer/agent.py."""

import pytest

from src.reviewer.agent import _extract_changed_paths


class TestExtractChangedPaths:
    def test_standard_diff_returns_all_paths(self):
        diff = (
            "### src/contracts/order_created.py\n"
            "@@ -1,5 +1,6 @@\n"
            "-order_id: str\n"
            "+order_id: int\n"
            "\n"
            "### src/schemas/order_created_payload.py\n"
            "@@ -10,3 +10,4 @@\n"
            " items: list\n"
            "+metadata: dict\n"
        )
        paths = _extract_changed_paths(diff)
        assert paths == [
            "src/contracts/order_created.py",
            "src/schemas/order_created_payload.py",
        ]

    def test_duplicate_paths_are_deduplicated(self):
        diff = (
            "### src/contracts/order_created.py\n"
            "@@ -1,5 +1,6 @@\n"
            " some content\n"
            "\n"
            "### src/contracts/order_created.py\n"
            "@@ -10,3 +10,4 @@\n"
            " more content\n"
        )
        paths = _extract_changed_paths(diff)
        assert paths == ["src/contracts/order_created.py"]

    def test_empty_diff_returns_empty_list(self):
        assert _extract_changed_paths("") == []

    def test_diff_with_no_headers_returns_empty_list(self):
        diff = (
            "@@ -1,5 +1,6 @@\n"
            "-order_id: str\n"
            "+order_id: int\n"
        )
        assert _extract_changed_paths(diff) == []

    def test_order_is_preserved(self):
        diff = (
            "### b.py\n"
            "@@ -1 +1 @@\n"
            " x\n"
            "### a.py\n"
            "@@ -1 +1 @@\n"
            " y\n"
            "### c.py\n"
            "@@ -1 +1 @@\n"
            " z\n"
        )
        paths = _extract_changed_paths(diff)
        assert paths == ["b.py", "a.py", "c.py"]

    def test_paths_use_raw_header_format_no_a_b_prefixes(self):
        """fetch_pr_data() uses '### filename' (no 'a/'/'b/' prefixes)."""
        diff = (
            "### src/knowledge/client.py\n"
            "@@ -0,0 +1,10 @@\n"
            "+import neo4j\n"
        )
        paths = _extract_changed_paths(diff)
        assert paths == ["src/knowledge/client.py"]
        # Verify no 'a/' or 'b/' prefix is included
        assert not paths[0].startswith("a/")
        assert not paths[0].startswith("b/")

    def test_multiple_files_multiple_hunks(self):
        """Multiple hunk headers under the same file produce one entry."""
        diff = (
            "### src/main.py\n"
            "@@ -1,3 +1,4 @@\n"
            " import os\n"
            "### src/utils.py\n"
            "@@ -5,2 +5,3 @@\n"
            " def foo():\n"
            "### src/main.py\n"
            "@@ -20,2 +21,3 @@\n"
            " def bar():\n"
        )
        paths = _extract_changed_paths(diff)
        # src/main.py appears twice but should be deduplicated
        assert paths.count("src/main.py") == 1
        assert "src/utils.py" in paths
        assert len(paths) == 2

    def test_whitespace_around_path_is_stripped(self):
        diff = "###   src/some/file.py   \n@@ -1 +1 @@\n x\n"
        paths = _extract_changed_paths(diff)
        assert paths == ["src/some/file.py"]

    def test_only_lines_starting_with_triple_hash_are_parsed(self):
        """Lines starting with ## or # or plain text must be ignored."""
        diff = (
            "## This is a section header\n"
            "# Single hash comment\n"
            "### src/valid.py\n"
            "@@ -1 +1 @@\n"
            " content\n"
        )
        paths = _extract_changed_paths(diff)
        assert paths == ["src/valid.py"]

    def test_topology_yaml_from_conftest(self, sample_diff):
        """Smoke test using the shared fixture from conftest."""
        paths = _extract_changed_paths(sample_diff)
        assert "src/contracts/order_created.py" in paths
        assert "src/schemas/order_created_payload.py" in paths
