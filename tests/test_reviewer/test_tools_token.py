"""Unit tests: fetch_pr_data github_token param takes priority over env var."""

from unittest.mock import MagicMock, patch


from src.reviewer.tools import fetch_pr_data, post_review_comments


# ---------------------------------------------------------------------------
# fetch_pr_data — github_token param
# ---------------------------------------------------------------------------


class TestFetchPrDataToken:
    def _make_mock_pr(self):
        mock_file = MagicMock()
        mock_file.filename = "src/main.py"
        mock_file.patch = "@@ -1 +1 @@\n-foo\n+bar"

        mock_pr = MagicMock()
        mock_pr.head.sha = "abc123"
        mock_pr.title = "Test PR"
        mock_pr.get_files.return_value = [mock_file]
        return mock_pr

    @patch("src.reviewer.tools.Github")
    def test_uses_param_token_when_provided(self, mock_github_cls):
        mock_github_cls.return_value.get_repo.return_value.get_pull.return_value = (
            self._make_mock_pr()
        )

        fetch_pr_data("owner", "repo", 1, github_token="param-token")

        mock_github_cls.assert_called_once_with("param-token")

    @patch("src.reviewer.tools.Github")
    @patch.dict("os.environ", {"GITHUB_ACCESS_TOKEN": "env-token"})
    def test_param_takes_priority_over_env_var(self, mock_github_cls):
        mock_github_cls.return_value.get_repo.return_value.get_pull.return_value = (
            self._make_mock_pr()
        )

        fetch_pr_data("owner", "repo", 1, github_token="param-token")

        # param-token, NOT env-token
        mock_github_cls.assert_called_once_with("param-token")

    @patch("src.reviewer.tools.Github")
    @patch.dict("os.environ", {"GITHUB_ACCESS_TOKEN": "env-token"})
    def test_falls_back_to_env_var_when_param_empty(self, mock_github_cls):
        mock_github_cls.return_value.get_repo.return_value.get_pull.return_value = (
            self._make_mock_pr()
        )

        fetch_pr_data("owner", "repo", 1, github_token="")

        mock_github_cls.assert_called_once_with("env-token")

    @patch("src.reviewer.tools.Github")
    def test_returns_diff_head_sha_title(self, mock_github_cls):
        mock_github_cls.return_value.get_repo.return_value.get_pull.return_value = (
            self._make_mock_pr()
        )

        diff_text, head_sha, pr_title = fetch_pr_data(
            "owner", "repo", 1, github_token="tok"
        )

        assert head_sha == "abc123"
        assert pr_title == "Test PR"
        assert "src/main.py" in diff_text


# ---------------------------------------------------------------------------
# post_review_comments — github_token param
# ---------------------------------------------------------------------------


class TestPostReviewCommentsToken:
    @patch("src.reviewer.tools.httpx.post")
    @patch.dict("os.environ", {"GITHUB_ACCESS_TOKEN": "env-token"})
    def test_param_takes_priority_over_env_var(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = "ok"

        post_review_comments(
            "owner", "repo", 1, "sha", "[]", github_token="param-token"
        )

        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs["headers"]
        assert headers["Authorization"] == "Bearer param-token"

    @patch("src.reviewer.tools.httpx.post")
    @patch.dict("os.environ", {"GITHUB_ACCESS_TOKEN": "env-token"})
    def test_falls_back_to_env_var_when_param_empty(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = "ok"

        post_review_comments("owner", "repo", 1, "sha", "[]", github_token="")

        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs["headers"]
        assert headers["Authorization"] == "Bearer env-token"

    @patch.dict("os.environ", {}, clear=True)
    def test_returns_error_when_no_token(self):
        # No param token, no env var
        result = post_review_comments("owner", "repo", 1, "sha", "[]", github_token="")
        assert "Error" in result
        assert "GITHUB_ACCESS_TOKEN" in result
