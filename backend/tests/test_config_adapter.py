"""Unit tests for backend/core/providers.py (migrated from src/ui/config_adapter.py)."""

import pytest

from backend.core.providers import PROVIDERS, build_provider_config, resolve_public_hf_role_configs


# ---------------------------------------------------------------------------
# Provider: cerebras
# ---------------------------------------------------------------------------


class TestCerebrasProvider:
    def test_returns_hf_router_base_url(self):
        model_id, base_url, api_key = build_provider_config(
            "cerebras", "meta-llama/Llama-3.1-8B-Instruct:cerebras", "hf-key-123"
        )
        assert base_url == "https://router.huggingface.co/v1"

    def test_returns_provided_api_key(self):
        model_id, base_url, api_key = build_provider_config(
            "cerebras", "meta-llama/Llama-3.1-8B-Instruct:cerebras", "hf-key-123"
        )
        assert api_key == "hf-key-123"

    def test_falls_back_to_default_model_when_empty(self):
        model_id, base_url, api_key = build_provider_config("cerebras", "", "hf-key")
        assert model_id == PROVIDERS["cerebras"]["default_model"]


# ---------------------------------------------------------------------------
# Provider: huggingface
# ---------------------------------------------------------------------------


class TestHuggingFaceProvider:
    def test_returns_correct_base_url(self):
        model_id, base_url, api_key = build_provider_config(
            "huggingface", "my-model", "hf-key-123"
        )
        assert base_url == "https://router.huggingface.co/v1"

    def test_returns_provided_model(self):
        model_id, base_url, api_key = build_provider_config(
            "huggingface", "my-model", "hf-key-123"
        )
        assert model_id == "my-model"

    def test_returns_provided_api_key(self):
        model_id, base_url, api_key = build_provider_config(
            "huggingface", "my-model", "hf-key-123"
        )
        assert api_key == "hf-key-123"

    def test_falls_back_to_default_model_when_empty(self):
        model_id, base_url, api_key = build_provider_config("huggingface", "", "hf-key")
        assert model_id == PROVIDERS["huggingface"]["default_model"]

    def test_falls_back_to_default_model_when_whitespace(self):
        model_id, base_url, api_key = build_provider_config(
            "huggingface", "   ", "hf-key"
        )
        assert model_id == PROVIDERS["huggingface"]["default_model"]

    def test_case_insensitive_provider(self):
        model_id, base_url, api_key = build_provider_config(
            "HuggingFace", "my-model", "hf-key"
        )
        assert base_url == "https://router.huggingface.co/v1"


# ---------------------------------------------------------------------------
# Provider: openai
# ---------------------------------------------------------------------------


class TestOpenAIProvider:
    def test_returns_correct_base_url(self):
        model_id, base_url, api_key = build_provider_config(
            "openai", "gpt-4o", "sk-test"
        )
        assert base_url == "https://api.openai.com/v1"

    def test_returns_provided_api_key(self):
        model_id, base_url, api_key = build_provider_config(
            "openai", "gpt-4o", "sk-test"
        )
        assert api_key == "sk-test"

    def test_falls_back_to_default_model_when_empty(self):
        model_id, base_url, api_key = build_provider_config("openai", "", "sk-test")
        assert model_id == PROVIDERS["openai"]["default_model"]


# ---------------------------------------------------------------------------
# Provider: ollama (special case — api_key always "ollama")
# ---------------------------------------------------------------------------


class TestOllamaProvider:
    def test_api_key_always_ollama_regardless_of_input(self):
        model_id, base_url, api_key = build_provider_config(
            "ollama", "llama3", "anything"
        )
        assert api_key == "ollama"

    def test_api_key_ollama_when_empty_input(self):
        model_id, base_url, api_key = build_provider_config("ollama", "llama3", "")
        assert api_key == "ollama"

    def test_returns_default_base_url_when_no_override(self):
        model_id, base_url, api_key = build_provider_config("ollama", "llama3", "")
        assert base_url == "http://localhost:11434/v1"

    def test_accepts_custom_base_url_override(self):
        model_id, base_url, api_key = build_provider_config(
            "ollama", "llama3", "", base_url_override="http://my-server:11434/v1"
        )
        assert base_url == "http://my-server:11434/v1"

    def test_falls_back_to_default_model_when_empty(self):
        model_id, base_url, api_key = build_provider_config("ollama", "", "")
        assert model_id == PROVIDERS["ollama"]["default_model"]


# ---------------------------------------------------------------------------
# resolve_public_hf_role_configs
# ---------------------------------------------------------------------------


class TestResolvePublicHfRoleConfigs:
    def test_returns_dict_with_all_roles(self):
        configs = resolve_public_hf_role_configs("user-hf-key")
        assert set(configs.keys()) == {"bug", "security", "cross_repo", "leader"}

    def test_uses_request_api_key_for_all_roles(self):
        configs = resolve_public_hf_role_configs("user-hf-key")
        for role, (_model, _base_url, api_key) in configs.items():
            assert api_key == "user-hf-key"

    def test_uses_hf_base_url_for_all_roles(self):
        configs = resolve_public_hf_role_configs("key")
        for role, (_model, base_url, _api_key) in configs.items():
            assert "huggingface" in base_url or "router.huggingface" in base_url


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestUnknownProvider:
    def test_raises_value_error_for_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            build_provider_config("anthropic", "claude-3", "sk-ant")
