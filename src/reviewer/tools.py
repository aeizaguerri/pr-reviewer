import json
import os

import httpx
from github import Github


def fetch_pr_data(owner: str, repo: str, pr_number: int) -> tuple[str, str, str]:
    """Fetches PR diff, head SHA, and title from GitHub using PyGithub.

    Args:
        owner: Repository owner (user or org).
        repo: Repository name.
        pr_number: Pull request number.

    Returns:
        Tuple of (diff_text, head_sha, pr_title).
        diff_text is a concatenation of filename + patch for each changed file.
    """
    token = os.getenv("GITHUB_ACCESS_TOKEN", "")
    g = Github(token) if token else Github()
    repository = g.get_repo(f"{owner}/{repo}")
    pr = repository.get_pull(pr_number)

    head_sha = pr.head.sha
    pr_title = pr.title

    diff_parts: list[str] = []
    for f in pr.get_files():
        if f.patch:
            diff_parts.append(f"### {f.filename}\n{f.patch}")

    diff_text = "\n\n".join(diff_parts)
    return diff_text, head_sha, pr_title


def post_review_comments(
    owner: str,
    repo: str,
    pr_number: int,
    commit_sha: str,
    comments: str,
    summary: str = "",
) -> str:
    """Posts a review with inline comments on a GitHub pull request.

    Args:
        owner: Repository owner (user or org).
        repo: Repository name.
        pr_number: Pull request number.
        commit_sha: SHA of the latest commit in the PR.
        comments: JSON string with a list of comment objects, each having:
                  {"path": str, "line": int, "body": str}
        summary: Optional overall review summary body text.

    Returns:
        Success message or error description.
    """
    token = os.getenv("GITHUB_ACCESS_TOKEN", "")
    if not token:
        return "Error: GITHUB_ACCESS_TOKEN is not set."

    try:
        parsed_comments = json.loads(comments) if isinstance(comments, str) else comments
    except json.JSONDecodeError as e:
        return f"Error parsing comments JSON: {e}"

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "commit_id": commit_sha,
        "body": summary,
        "event": "COMMENT",
        "comments": [
            {"path": c["path"], "line": c["line"], "body": c["body"]}
            for c in parsed_comments
        ],
    }

    response = httpx.post(url, headers=headers, json=payload, timeout=30)

    if response.status_code in (200, 201):
        return f"Review posted successfully on PR #{pr_number} in {owner}/{repo}."
    return f"GitHub API error {response.status_code}: {response.text}"
