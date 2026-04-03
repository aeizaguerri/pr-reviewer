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

from src.core.logging_config import configure_logging

configure_logging()

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

# ---------------------------------------------------------------------------
# Theme — dark/light toggle
# ---------------------------------------------------------------------------

# config.toml sets base="dark" as native default.
# Light mode is applied via CSS injection that overrides every Streamlit
# CSS variable and explicitly targets each component type.
# Using data-testid selectors (stable across versions) instead of generated
# class names.

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

# CSS transitions are always injected so that switching feels smooth.
_TRANSITIONS_CSS = """
<style>
    .stApp,
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] > div,
    [data-testid="stSidebarContent"],
    [data-testid="stHeader"],
    [data-testid="stMainBlockContainer"],
    .stTextInput input,
    [data-baseweb="input"],
    [data-baseweb="select"] > div:first-child,
    [data-testid="stMarkdownContainer"],
    [data-testid="stWidgetLabel"],
    [data-testid="stAlert"],
    [data-testid="metric-container"],
    button,
    hr {
        transition:
            background-color 0.3s ease,
            color 0.3s ease,
            border-color 0.3s ease,
            box-shadow 0.3s ease !important;
    }
    svg, svg path, svg rect, svg circle, svg polygon {
        transition: fill 0.3s ease, stroke 0.3s ease !important;
    }
</style>
"""

# Light mode: exhaustive overrides of every Streamlit dark default.
# Organised by component so it's easy to extend.
_LIGHT_MODE_CSS = """
<style>

/* ── 1. CSS VARIABLE ROOT OVERRIDES ─────────────────────────────────────── */
:root {
    --background-color:           #ffffff !important;
    --secondary-background-color: #f0f2f6 !important;
    --text-color:                 #31333f !important;
    --primary-color:              #FF4B4B !important;
}

/* ── 2. APP CHROME ───────────────────────────────────────────────────────── */
.stApp {
    background-color: #ffffff !important;
    color: #31333f !important;
}
[data-testid="stMainBlockContainer"],
.main .block-container {
    background-color: #ffffff !important;
}
[data-testid="stHeader"] {
    background-color: #ffffff !important;
    border-bottom: 1px solid rgba(49,51,63,0.1) !important;
}
/* Streamlit's top coloured bar */
[data-testid="stDecoration"] {
    background-image: none !important;
    background-color: #FF4B4B !important;
}

/* ── 3. SIDEBAR ──────────────────────────────────────────────────────────── */
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div:first-child,
[data-testid="stSidebarContent"] {
    background-color: #f0f2f6 !important;
}
/* Text inside sidebar */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] span:not([data-baseweb]),
[data-testid="stSidebar"] label {
    color: #31333f !important;
}
/* Sidebar collapse/expand button */
[data-testid="stSidebarCollapseButton"] svg,
[data-testid="collapsedControl"] svg,
[data-testid="stSidebarNavCollapseIcon"] svg {
    fill: #31333f !important;
}

/* ── 4. GENERAL TEXT ─────────────────────────────────────────────────────── */
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] a,
[data-testid="stMarkdownContainer"] strong,
[data-testid="stMarkdownContainer"] em,
[data-testid="stMarkdownContainer"] code,
[data-testid="stHeadingWithActionElements"] h1,
[data-testid="stHeadingWithActionElements"] h2,
[data-testid="stHeadingWithActionElements"] h3,
.stHeader > h1, .stHeader > h2, .stHeader > h3,
p, li {
    color: #31333f !important;
}

/* ── 5. WIDGET LABELS ────────────────────────────────────────────────────── */
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] span,
label {
    color: #31333f !important;
}

/* ── 6. TEXT INPUT ───────────────────────────────────────────────────────── */
/* Outer border wrapper */
[data-baseweb="input"] {
    background-color: #ffffff !important;
    border-color: rgba(49,51,63,0.2) !important;
}
/* Actual <input> element */
.stTextInput input,
[data-baseweb="input"] input {
    background-color: #ffffff !important;
    color: #31333f !important;
    caret-color: #31333f !important;
}
/* Placeholder text */
.stTextInput input::placeholder,
[data-baseweb="input"] input::placeholder {
    color: rgba(49,51,63,0.38) !important;
    opacity: 1 !important;
}
/* Focus ring */
.stTextInput input:focus,
[data-baseweb="input"]:focus-within {
    border-color: #FF4B4B !important;
    box-shadow: 0 0 0 1px #FF4B4B !important;
}
/* Icon inside input (e.g. password eye) */
.stTextInput svg {
    fill: rgba(49,51,63,0.5) !important;
}
/* Password visibility toggle button (sits inside the input wrapper) */
.stTextInput button,
[data-baseweb="input"] button {
    background-color: #f0f2f6 !important;
    border-color: rgba(49,51,63,0.2) !important;
}
.stTextInput button:hover,
[data-baseweb="input"] button:hover {
    background-color: #e2e5ea !important;
}
.stTextInput button svg,
[data-baseweb="input"] button svg {
    fill: rgba(49,51,63,0.6) !important;
}

/* ── 7. SELECT BOX ───────────────────────────────────────────────────────── */
/* Control (closed state) */
[data-baseweb="select"] > div:first-child {
    background-color: #ffffff !important;
    border-color: rgba(49,51,63,0.2) !important;
}
[data-baseweb="select"] > div:first-child > div {
    background-color: #ffffff !important;
    color: #31333f !important;
}
/* Selected value text */
[data-baseweb="select"] span,
[data-baseweb="select"] [data-testid="stMarkdownContainer"] p {
    color: #31333f !important;
}
/* Chevron icon */
[data-baseweb="select"] svg {
    fill: rgba(49,51,63,0.6) !important;
}
/* Dropdown popover / menu */
[data-baseweb="popover"],
[data-baseweb="popover"] > div,
[data-baseweb="menu"],
ul[data-baseweb="menu"] {
    background-color: #ffffff !important;
    border-color: rgba(49,51,63,0.1) !important;
}
li[role="option"],
[data-baseweb="option"] {
    background-color: #ffffff !important;
    color: #31333f !important;
}
li[role="option"]:hover,
[data-baseweb="option"]:hover,
[aria-selected="true"][data-baseweb="option"] {
    background-color: #f0f2f6 !important;
}

/* ── 8. HELP / TOOLTIP ICON (?) ─────────────────────────────────────────── */
[data-testid="stTooltipIcon"] svg,
.stTooltipIcon svg {
    fill: rgba(49,51,63,0.4) !important;
}

/* ── 9. TOOLBAR / HEADER BUTTONS ─────────────────────────────────────────── */
[data-testid="stHeader"] svg,
[data-testid="baseButton-headerNoPadding"] svg,
[data-testid="stToolbarActionButton"] svg {
    fill: #31333f !important;
}

/* ── 10. ALERT / NOTIFICATION BOXES ─────────────────────────────────────── */
/* Generic alert wrapper */
[data-testid="stAlert"] > div {
    border-color: rgba(49,51,63,0.15) !important;
}
/* Warning ⚠️ */
[data-testid="stNotificationContentWarning"] {
    background-color: rgba(255,193,7,0.12) !important;
    color: #7d5700 !important;
    border-left-color: #f59e0b !important;
}
[data-testid="stNotificationContentWarning"] p,
[data-testid="stNotificationContentWarning"] span {
    color: #7d5700 !important;
}
[data-testid="stNotificationContentWarning"] svg {
    fill: #f59e0b !important;
}
/* Error ❌ */
[data-testid="stNotificationContentError"] {
    background-color: rgba(255,75,75,0.12) !important;
    color: #7d0000 !important;
    border-left-color: #ef4444 !important;
}
[data-testid="stNotificationContentError"] p,
[data-testid="stNotificationContentError"] span {
    color: #7d0000 !important;
}
[data-testid="stNotificationContentError"] svg {
    fill: #ef4444 !important;
}
/* Success ✅ */
[data-testid="stNotificationContentSuccess"] {
    background-color: rgba(33,195,84,0.12) !important;
    color: #065f46 !important;
    border-left-color: #22c55e !important;
}
[data-testid="stNotificationContentSuccess"] p,
[data-testid="stNotificationContentSuccess"] span {
    color: #065f46 !important;
}
[data-testid="stNotificationContentSuccess"] svg {
    fill: #22c55e !important;
}
/* Info ℹ️ */
[data-testid="stNotificationContentInfo"] {
    background-color: rgba(61,157,243,0.12) !important;
    color: #1e3a8a !important;
    border-left-color: #3b82f6 !important;
}
[data-testid="stNotificationContentInfo"] p,
[data-testid="stNotificationContentInfo"] span {
    color: #1e3a8a !important;
}
[data-testid="stNotificationContentInfo"] svg {
    fill: #3b82f6 !important;
}

/* ── 11. METRIC ──────────────────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background-color: transparent !important;
}
[data-testid="stMetricLabel"],
[data-testid="stMetricLabel"] p,
[data-testid="stMetricValue"],
[data-testid="stMetricValue"] div,
[data-testid="stMetricDelta"] {
    color: #31333f !important;
}

/* ── 12. BUTTONS ─────────────────────────────────────────────────────────── */
/* Primary — both old and new data-testid for Streamlit 1.45+ */
[data-testid="stBaseButton-primary"],
[data-testid="baseButton-primary"],
.stButton > button[kind="primary"] {
    background-color: #FF4B4B !important;
    color: #ffffff !important;
    border-color: #FF4B4B !important;
}
[data-testid="stBaseButton-primary"] svg,
[data-testid="baseButton-primary"] svg,
.stButton > button[kind="primary"] svg {
    fill: #ffffff !important;
}
/* Secondary — explicit light background (transparent inherits dark base) */
[data-testid="stBaseButton-secondary"],
[data-testid="baseButton-secondary"],
.stButton > button[kind="secondary"] {
    background-color: #f0f2f6 !important;
    color: #31333f !important;
    border-color: rgba(49,51,63,0.2) !important;
}
[data-testid="stBaseButton-secondary"] svg,
[data-testid="baseButton-secondary"] svg,
.stButton > button[kind="secondary"] svg {
    fill: #31333f !important;
}

/* ── 13. DATAFRAME ───────────────────────────────────────────────────────── */
[data-testid="stDataFrame"],
.dvn-scroller,
.stDataFrame {
    background-color: #ffffff !important;
    color: #31333f !important;
}

/* ── 14. DIVIDERS ────────────────────────────────────────────────────────── */
hr {
    border-color: rgba(49,51,63,0.15) !important;
}

/* ── 15. RADIO BUTTONS ───────────────────────────────────────────────────── */
[data-testid="stRadio"] p,
[data-testid="stRadio"] label,
[data-testid="stRadio"] span {
    color: #31333f !important;
}

/* ── 16. CAPTIONS / SMALL TEXT ───────────────────────────────────────────── */
.stCaption,
[data-testid="stCaptionContainer"] p {
    color: rgba(49,51,63,0.55) !important;
}

/* ── 17. SPINNER ─────────────────────────────────────────────────────────── */
[data-testid="stSpinner"] p {
    color: #31333f !important;
}

</style>
"""

# Inject CSS — transitions always, light overrides conditionally.
st.markdown(_TRANSITIONS_CSS, unsafe_allow_html=True)
if not st.session_state.dark_mode:
    st.markdown(_LIGHT_MODE_CSS, unsafe_allow_html=True)

# Custom CSS for horizontal scrolling on dataframes (always active)
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
        "Could not connect to the backend. Using fallback provider list.",
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

    # ── Theme toggle ───────────────────────────────────────────────────────
    col_dark, col_light = st.columns(2)
    with col_dark:
        dark_btn = st.button(
            "🌙 Oscuro",
            use_container_width=True,
            type="primary" if st.session_state.dark_mode else "secondary",
            help="Cambiar a modo oscuro",
        )
    with col_light:
        light_btn = st.button(
            "☀️ Claro",
            use_container_width=True,
            type="primary" if not st.session_state.dark_mode else "secondary",
            help="Cambiar a modo claro",
        )

    if dark_btn and not st.session_state.dark_mode:
        st.session_state.dark_mode = True
        st.rerun()
    if light_btn and st.session_state.dark_mode:
        st.session_state.dark_mode = False
        st.rerun()

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
            "base_url_override": base_url_input,
        }

        request_headers = {"X-GitHub-Token": github_token}
        if provider_api_key:
            request_headers["Authorization"] = f"Bearer {provider_api_key}"

        with st.spinner(f"Reviewing PR #{pr_num} in {owner}/{repo}…"):
            try:
                response = httpx.post(
                    f"{BACKEND_URL}/api/v1/review",
                    json=payload,
                    headers=request_headers,
                    timeout=300,
                )
                response.raise_for_status()
                result = response.json()
            except httpx.ConnectError:
                st.error("❌ Backend unreachable. Is the backend service running?")
                st.stop()
            except httpx.HTTPStatusError as exc:
                st.error(f"Backend error {exc.response.status_code}: {exc.response.text}")
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
