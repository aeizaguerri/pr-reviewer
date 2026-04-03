"""Provider configuration for the backend API.

Migrated from src/ui/config_adapter.py — same logic, same provider keys.
"""

from backend.core.config import BackendConfig
from backend.models.schemas import ProviderInfo

# Models that support structured outputs (Pydantic schema)
# Cerebras and OpenAI support it; HuggingFace standard and Ollama don't
SUPPORTS_STRUCTURED_OUTPUT: dict[str, bool] = {
    "openai": True,  # All OpenAI models
    "cerebras": True,  # Cerebras supports structured outputs via HF router
    "huggingface": False,  # Standard HF doesn't support it
    "ollama": False,  # Ollama doesn't support it well
}

PROVIDERS: dict[str, dict[str, str]] = {
    "cerebras": {
        "base_url": "https://router.huggingface.co/v1",
        "key_label": "HuggingFace API Key",
        "default_model": "meta-llama/Llama-3.1-8B-Instruct:cerebras",
        "description": "FREE - 1M tokens/day, very fast",
    },
    "huggingface": {
        "base_url": "https://router.huggingface.co/v1",
        "key_label": "HuggingFace API Key",
        "default_model": "moonshotai/Kimi-K2-Instruct",
        "description": "Uses standard HF inference (no structured outputs)",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "key_label": "OpenAI API Key",
        "default_model": "gpt-4o-mini",
        "description": "Paid - requires OpenAI API key",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "key_label": "Not required",
        "default_model": "llama3",
        "description": "Local - requires Ollama running",
    },
}


def build_provider_config(
    provider: str,
    model: str,
    api_key: str,
    base_url_override: str = "",
) -> tuple[str, str, str]:
    """Build (model_id, base_url, api_key) from form inputs.

    Args:
        provider: One of "cerebras", "huggingface", "openai", "ollama".
        model: Model ID string. If empty, falls back to provider default.
        api_key: API key string. For ollama, always replaced with "ollama".
        base_url_override: Custom base URL (used for ollama custom endpoint).

    Returns:
        Tuple of (model_id, base_url, api_key) matching Config.get_model_config() shape.

    Raises:
        ValueError: If the provider is not in PROVIDERS.
    """
    provider = provider.lower()
    if provider not in PROVIDERS:
        raise ValueError(
            f"Unknown provider: '{provider}'. Must be one of {list(PROVIDERS)}"
        )

    provider_info = PROVIDERS[provider]
    model_id = (
        model.strip() if model and model.strip() else provider_info["default_model"]
    )
    base_url = (
        base_url_override.strip()
        if base_url_override and base_url_override.strip()
        else provider_info["base_url"]
    )

    # Ollama never needs a real API key
    if provider == "ollama":
        resolved_key = "ollama"
    elif api_key and api_key.strip():
        resolved_key = api_key
    elif provider == "openai":
        resolved_key = BackendConfig.OPENAI_API_KEY
    else:
        # cerebras and huggingface both use the HF key
        resolved_key = BackendConfig.HUGGING_FACE_API_KEY

    return model_id, base_url, resolved_key


def get_all_providers() -> list[ProviderInfo]:
    """Returns a list of ProviderInfo objects for all configured providers."""
    return [
        ProviderInfo(
            key=key,
            description=info["description"],
            default_model=info["default_model"],
            key_label=info["key_label"],
            supports_structured_output=SUPPORTS_STRUCTURED_OUTPUT.get(key, False),
        )
        for key, info in PROVIDERS.items()
    ]
