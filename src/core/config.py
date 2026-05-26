import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Centralised application configuration loaded from environment variables."""

    STRUCTURED_OUTPUT_PROVIDERS: set[str] = {"openai", "cerebras"}

    # HuggingFace
    HUGGING_FACE_API_KEY: str = os.getenv("HUGGING_FACE_API_KEY", "")
    HUGGING_FACE_API_URL: str = os.getenv(
        "HUGGING_FACE_API_URL", "https://router.huggingface.co/v1"
    )

    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Ollama
    OLLAMA_API_URL: str = os.getenv("OLLAMA_API_URL", "http://localhost:11434/v1")

    # GitHub
    GITHUB_ACCESS_TOKEN: str = os.getenv("GITHUB_ACCESS_TOKEN", "")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Default provider / model
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "moonshotai/Kimi-K2-Instruct")
    DEFAULT_PROVIDER: str = os.getenv("DEFAULT_PROVIDER", "huggingface")

    # Per-role model overrides (public HF path)
    REVIEW_BUG_MODEL: str = os.getenv("REVIEW_BUG_MODEL", "")
    REVIEW_SECURITY_MODEL: str = os.getenv("REVIEW_SECURITY_MODEL", "")
    REVIEW_CROSS_REPO_MODEL: str = os.getenv("REVIEW_CROSS_REPO_MODEL", "")
    REVIEW_LEADER_MODEL: str = os.getenv("REVIEW_LEADER_MODEL", "")

    # Neo4j
    NEO4J_URI: str = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "")

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration. Raises ValueError if invalid."""
        if cls.ENABLE_GRAPH_ENRICHMENT:
            if not cls.NEO4J_PASSWORD:
                raise ValueError("NEO4J_PASSWORD is required when ENABLE_GRAPH_ENRICHMENT is true")
            if not cls.NEO4J_URI:
                raise ValueError("NEO4J_URI is required when ENABLE_GRAPH_ENRICHMENT is true")

    # Knowledge Graph
    ENABLE_GRAPH_ENRICHMENT: bool = os.getenv("ENABLE_GRAPH_ENRICHMENT", "false").lower() == "true"
    GRAPH_QUERY_TIMEOUT: int = int(os.getenv("GRAPH_QUERY_TIMEOUT", "5"))
    MAX_IMPACT_WARNINGS: int = int(os.getenv("MAX_IMPACT_WARNINGS", "10"))

    # Prompt injection defense
    MAX_DIFF_CHARS: int = int(os.getenv("MAX_DIFF_CHARS", "100000"))
    TRUSTED_AUTHOR_ASSOCIATIONS: str = os.getenv(
        "TRUSTED_AUTHOR_ASSOCIATIONS", "OWNER,MEMBER,COLLABORATOR"
    )

    # Specialist reviewer timeout
    REVIEW_SPECIALIST_TIMEOUT_SECONDS: int = int(
        os.getenv("REVIEW_SPECIALIST_TIMEOUT_SECONDS", "120")
    )

    # Opik
    OPIK_API_KEY: str = os.getenv("OPIK_API_KEY", "")
    OPIK_PROJECT_NAME: str = os.getenv("OPIK_PROJECT_NAME", "pr-reviewer")
    OPIK_WORKSPACE: str = os.getenv("OPIK_WORKSPACE", "")

    @classmethod
    def get_model_config(cls) -> tuple[str, str, str]:
        """Returns (model_id, base_url, api_key) for the configured DEFAULT_PROVIDER."""
        provider = cls.DEFAULT_PROVIDER.lower()
        if provider == "openai":
            return cls.DEFAULT_MODEL, "https://api.openai.com/v1", cls.OPENAI_API_KEY
        if provider == "ollama":
            return cls.DEFAULT_MODEL, cls.OLLAMA_API_URL, "ollama"
        # Cerebras is served through the Hugging Face router with the HF key.
        return cls.DEFAULT_MODEL, cls.HUGGING_FACE_API_URL, cls.HUGGING_FACE_API_KEY

    @classmethod
    def provider_supports_structured_output(cls, provider: str) -> bool:
        return provider.lower() in cls.STRUCTURED_OUTPUT_PROVIDERS

    @classmethod
    def resolve_role_configs(cls, api_key: str) -> dict[str, tuple[str, str, str]]:
        """Resolve per-role (model_id, base_url, api_key) for the public HF path.

        Args:
            api_key: The request-scoped Hugging Face API key.

        Returns:
            dict mapping role name -> (model_id, base_url, api_key).
            Role-specific env vars override DEFAULT_MODEL when set.
        """
        base_url = cls.HUGGING_FACE_API_URL
        return {
            "bug": (cls.REVIEW_BUG_MODEL or cls.DEFAULT_MODEL, base_url, api_key),
            "security": (cls.REVIEW_SECURITY_MODEL or cls.DEFAULT_MODEL, base_url, api_key),
            "cross_repo": (cls.REVIEW_CROSS_REPO_MODEL or cls.DEFAULT_MODEL, base_url, api_key),
            "leader": (cls.REVIEW_LEADER_MODEL or cls.DEFAULT_MODEL, base_url, api_key),
        }
