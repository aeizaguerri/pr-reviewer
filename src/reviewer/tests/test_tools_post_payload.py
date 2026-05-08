"""Unit tests: post_review_comments() payload structure.

Phase 2 (RED): Assert that every comment dict in the payload sent to GitHub
contains "side": "RIGHT". This test MUST FAIL until the field is added.

Phase 3 (GREEN): After adding "side": "RIGHT" in tools.py, all tests pass.
"""

import json
from unittest.mock import MagicMock, patch


from src.reviewer.tools import post_review_comments

SAMPLE_COMMENTS = json.dumps(
    [
        {"path": "src/main.py", "line": 10, "body": "Missing null check"},
        {"path": "src/utils.py", "line": 42, "body": "Inefficient loop"},
    ]
)


class TestPostReviewCommentsPayload:
    """Assert the comment dicts sent to GitHub contain 'side': 'RIGHT'."""

    @patch("src.reviewer.tools.httpx.post")
    def test_each_comment_has_side_right(self, mock_post):
        """Every comment dict in the payload MUST have side='RIGHT'."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_post.return_value = mock_response

        post_review_comments(
            "owner",
            "repo",
            1,
            "abc123",
            SAMPLE_COMMENTS,
            summary="LGTM",
            github_token="tok",
        )

        assert mock_post.called, "httpx.post was never called"
        actual_payload = mock_post.call_args.kwargs["json"]
        comments_sent = actual_payload["comments"]

        assert len(comments_sent) == 2, "Expected 2 comments in payload"
        for comment in comments_sent:
            assert "side" in comment, f"Comment dict missing 'side' field: {comment}"
            assert comment["side"] == "RIGHT", (
                f"Expected side='RIGHT', got side='{comment['side']}'"
            )


class TestPostReviewComments422Fallback:
    """Assert that the 422 fallback posts a top-level review with empty comments."""

    @patch("src.reviewer.tools.httpx.post")
    def test_fallback_payload_has_empty_comments(self, mock_post):
        """On 422, fallback payload must have comments=[] (no inline positions)."""
        first_response = MagicMock()
        first_response.status_code = 422
        first_response.text = "Unprocessable Entity"

        second_response = MagicMock()
        second_response.status_code = 201
        second_response.text = "ok"

        mock_post.side_effect = [first_response, second_response]

        result = post_review_comments(
            "owner",
            "repo",
            1,
            "abc123",
            SAMPLE_COMMENTS,
            summary="LGTM",
            github_token="tok",
        )

        assert mock_post.call_count == 2, "Expected two httpx.post calls (inline + fallback)"

        fallback_payload = mock_post.call_args_list[1].kwargs["json"]
        assert fallback_payload["comments"] == [], (
            f"Fallback payload should have empty 'comments', got: {fallback_payload['comments']}"
        )
        assert "top-level" in result or "inline positions" in result
