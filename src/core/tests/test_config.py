from unittest.mock import patch

from src.core.config import Config


class TestResolveRoleConfigs:
    """Verify per-role model resolution from environment variables with DEFAULT_MODEL fallback."""

    def test_all_role_env_vars_set_returns_configured_models(self):
        with patch.object(Config, "DEFAULT_MODEL", "default/model"):
            with patch.object(Config, "REVIEW_BUG_MODEL", "bug/model"):
                with patch.object(Config, "REVIEW_SECURITY_MODEL", "security/model"):
                    with patch.object(Config, "REVIEW_CROSS_REPO_MODEL", "cross/model"):
                        with patch.object(Config, "REVIEW_LEADER_MODEL", "leader/model"):
                            with patch.object(Config, "HUGGING_FACE_API_URL", "https://router.huggingface.co/v1"):
                                configs = Config.resolve_role_configs("user-hf-key")
                                assert configs["bug"] == ("bug/model", "https://router.huggingface.co/v1", "user-hf-key")
                                assert configs["security"] == ("security/model", "https://router.huggingface.co/v1", "user-hf-key")
                                assert configs["cross_repo"] == ("cross/model", "https://router.huggingface.co/v1", "user-hf-key")
                                assert configs["leader"] == ("leader/model", "https://router.huggingface.co/v1", "user-hf-key")

    def test_missing_role_vars_fallback_to_default_model(self):
        with patch.object(Config, "DEFAULT_MODEL", "default/model"):
            with patch.object(Config, "HUGGING_FACE_API_URL", "https://custom.huggingface.co/v1"):
                for attr in ("REVIEW_BUG_MODEL", "REVIEW_SECURITY_MODEL", "REVIEW_CROSS_REPO_MODEL", "REVIEW_LEADER_MODEL"):
                    patch.object(Config, attr, "").start()
                configs = Config.resolve_role_configs("api-key")
                for role in ("bug", "security", "cross_repo", "leader"):
                    model_id, base_url, api_key = configs[role]
                    assert model_id == "default/model"
                    assert base_url == "https://custom.huggingface.co/v1"
                    assert api_key == "api-key"

    def test_partial_role_env_vars_mix_configured_and_fallback(self):
        with patch.object(Config, "DEFAULT_MODEL", "default/model"):
            with patch.object(Config, "REVIEW_BUG_MODEL", "bug/override"):
                with patch.object(Config, "HUGGING_FACE_API_URL", "https://router.huggingface.co/v1"):
                    for attr in ("REVIEW_SECURITY_MODEL", "REVIEW_CROSS_REPO_MODEL", "REVIEW_LEADER_MODEL"):
                        patch.object(Config, attr, "").start()
                    configs = Config.resolve_role_configs("key")
                    assert configs["bug"] == ("bug/override", "https://router.huggingface.co/v1", "key")
                    assert configs["security"][0] == "default/model"
                    assert configs["cross_repo"][0] == "default/model"
                    assert configs["leader"][0] == "default/model"

    def test_default_model_fallback_to_hardcoded_when_no_env(self):
        with patch.object(Config, "DEFAULT_MODEL", "moonshotai/Kimi-K2-Instruct"):
            with patch.object(Config, "HUGGING_FACE_API_URL", "https://router.huggingface.co/v1"):
                for attr in ("REVIEW_BUG_MODEL", "REVIEW_SECURITY_MODEL", "REVIEW_CROSS_REPO_MODEL", "REVIEW_LEADER_MODEL"):
                    patch.object(Config, attr, "").start()
                configs = Config.resolve_role_configs("key")
                expected_default = "moonshotai/Kimi-K2-Instruct"
                for role in ("bug", "security", "cross_repo", "leader"):
                    assert configs[role][0] == expected_default
