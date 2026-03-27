"""Streamlit web UI for PR Code Reviewer.

Two-panel layout:
- Sidebar: LLM provider selection, API key input, GitHub token, model override
- Main area: PR input form (owner/repo + PR number), results display

Keys are stored in st.session_state only — never logged or persisted to disk.
All backend calls go through httpx to the backend API service.
"""

import os
import re

import httpx
import streamlit as st
from streamlit import column_config

# ---------------------------------------------------------------------------
# Backend URL configuration
# ---------------------------------------------------------------------------

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="PR Code Reviewer",
    page_icon="🔍",
    layout="wide",
)

# Custom CSS for horizontal scrolling on dataframes
st.markdown(
    """
<style>
    .stDataFrame {
        overflow-x: auto;
    }
    [data-testid="stDataFrame"] {
        overflow-x: auto !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Load providers from backend API
# ---------------------------------------------------------------------------


@st.cache_data(ttl=300)
def load_providers() -> dict[str, dict]:
    """Fetch provider list from backend. Returns empty dict on failure."""
    try:
        response = httpx.get(f"{BACKEND_URL}/api/v1/providers", timeout=10)
        response.raise_for_status()
        data = response.json()
        return {p["key"]: p for p in data["providers"]}
    except httpx.ConnectError:
        return {}
    except Exception:
        return {}


PROVIDERS = load_providers()

if not PROVIDERS:
    st.warning(
        "⚠️ Could not connect to the backend. Using fallback provider list.",
        icon="⚠️",
    )
    # Fallback provider list for graceful degradation
    PROVIDERS = {
        "cerebras": {
            "key": "cerebras",
            "description": "FREE - 1M tokens/day, very fast",
            "default_model": "meta-llama/Llama-3.1-8B-Instruct:cerebras",
            "key_label": "HuggingFace API Key",
            "supports_structured_output": True,
        }
    }

# ---------------------------------------------------------------------------
# Sidebar: configuration controls
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🔍 PR Code Reviewer")
    st.markdown("---")

    # Backend connectivity status
    try:
        health = httpx.get(f"{BACKEND_URL}/health", timeout=5.0)
        health_data = health.json()
        neo4j_ok = health_data.get("neo4j", False)
        st.success("Backend conectado ✓")
        if not neo4j_ok:
            st.warning("Neo4j no disponible — Graph enrichment desactivado")
    except Exception:
        st.error("Backend no disponible")

    st.markdown("---")
    st.subheader("LLM Provider")

    # Build options with descriptions
    provider_options = list(PROVIDERS.keys())
    provider_descriptions = {k: v.get("description", "") for k, v in PROVIDERS.items()}

    # Display provider with description
    provider = st.selectbox(
        "Provider",
        options=provider_options,
        key="provider",
        format_func=lambda x: f"{x} - {provider_descriptions[x]}"
        if provider_descriptions.get(x)
        else x,
    )

    # Conditional API key / base URL input depending on provider
    if provider == "ollama":
        base_url_input = st.text_input(
            "Ollama Base URL",
            value="http://localhost:11434/v1",
            key="ollama_base_url",
        )
        provider_api_key = ""  # not used for ollama
    else:
        key_label = PROVIDERS[provider]["key_label"]
        provider_api_key = st.text_input(
            key_label,
            type="password",
            key="provider_api_key",
            placeholder="sk-...",
        )
        base_url_input = ""

    st.markdown("---")
    st.subheader("GitHub")

    github_token = st.text_input(
        "GitHub Token",
        type="password",
        key="github_token",
        placeholder="ghp_...",
        help="Personal access token with repo read permissions.",
    )

    st.markdown("---")
    st.subheader("Model (optional)")

    model_override = st.text_input(
        "Model ID override",
        key="model_override",
        placeholder=f"Default: {PROVIDERS[provider]['default_model']}",
        help="Leave empty to use the provider default model.",
    )

# ---------------------------------------------------------------------------
# Main area: PR review form
# ---------------------------------------------------------------------------

st.header("Review a Pull Request")

col1, col2 = st.columns([3, 1])

with col1:
    repo_slug = st.text_input(
        "Repository (owner/repo)",
        key="repo_slug",
        placeholder="octocat/Hello-World",
    )

with col2:
    pr_number_input = st.text_input(
        "PR Number",
        key="pr_number",
        placeholder="42",
    )

review_button = st.button("🚀 Review PR", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _validate_inputs() -> bool:
    """Validate form inputs. Show st.error / st.warning on failure.

    Returns True only when all inputs are valid.
    """
    valid = True

    # Provider-specific API key check (not needed for ollama)
    if provider != "ollama" and not provider_api_key:
        st.error(f"{PROVIDERS[provider]['key_label']} is required")
        valid = False

    # GitHub token is always required
    if not github_token:
        st.error("GitHub token is required to fetch PR data")
        valid = False

    # Repository format
    if not repo_slug:
        st.warning("Repository slug is required")
        valid = False
    elif not REPO_PATTERN.match(repo_slug):
        st.warning("Repository must be in 'owner/repo' format")
        valid = False

    # PR number
    if not pr_number_input:
        st.warning("PR number is required")
        valid = False
    else:
        try:
            pr_num = int(pr_number_input)
            if pr_num <= 0:
                raise ValueError("non-positive")
        except ValueError:
            st.warning("PR number must be a positive integer")
            valid = False

    return valid


# ---------------------------------------------------------------------------
# Review execution
# ---------------------------------------------------------------------------

if review_button:
    if _validate_inputs():
        owner, repo = repo_slug.split("/", 1)
        pr_num = int(pr_number_input)

        payload = {
            "owner": owner,
            "repo": repo,
            "pr_number": pr_num,
            "provider": provider,
            "model": model_override,
            "api_key": provider_api_key,
            "base_url_override": base_url_input,
            "github_token": github_token,
        }

        with st.spinner(f"Reviewing PR #{pr_num} in {owner}/{repo}…"):
            try:
                response = httpx.post(
                    f"{BACKEND_URL}/api/v1/review",
                    json=payload,
                    timeout=300,
                )
                response.raise_for_status()
                result = response.json()
            except httpx.ConnectError:
                st.error("❌ Backend unreachable. Is the backend service running?")
                st.stop()
            except httpx.HTTPStatusError as exc:
                st.error(
                    f"Backend error {exc.response.status_code}: {exc.response.text}"
                )
                st.stop()
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}")
                st.stop()

        # ------------------------------------------------------------------
        # Results display
        # ------------------------------------------------------------------

        st.markdown("---")
        st.subheader("Review Results")

        # Approval badge via st.metric
        approved = result.get("approved", False)
        approval_label = "✅ Approved" if approved else "❌ Changes Requested"
        approval_delta = "Ready to merge" if approved else "Requires changes"
        st.metric(label="Decision", value=approval_label, delta=approval_delta)

        # Summary
        st.markdown("### Summary")
        st.markdown(result.get("summary", ""))

        # Bug table or success message
        bugs = result.get("bugs", [])
        if not bugs:
            st.success("🎉 No bugs found — PR looks clean!")
        else:
            st.markdown(f"### Bugs Found ({len(bugs)})")

            # Build rows with severity color prefix for display
            _SEVERITY_EMOJI = {"critical": "🔴", "major": "🟠", "minor": "🟡"}

            bug_rows = [
                {
                    "Severity": f"{_SEVERITY_EMOJI.get(bug['severity'], '')} {bug['severity']}",
                    "File": bug["file"],
                    "Line": bug["line"],
                    "Description": bug["description"],
                    "Suggestion": bug["suggestion"],
                }
                for bug in bugs
            ]

            # Use a scrollable container for the table
            with st.container():
                st.dataframe(
                    bug_rows,
                    use_container_width=True,
                    hide_index=True,
                    height=400,
                    column_config={
                        "Severity": column_config.TextColumn(width="small"),
                        "File": column_config.TextColumn(width="medium"),
                        "Line": column_config.NumberColumn(width="small"),
                        "Description": column_config.TextColumn(width="large"),
                        "Suggestion": column_config.TextColumn(width="large"),
                    },
                )

        # Impact warnings (from knowledge graph, optional)
        impact_warnings = result.get("impact_warnings", [])
        if impact_warnings:
            st.markdown("### ⚠️ Impact Warnings")
            for warning in impact_warnings:
                st.warning(warning["description"])
