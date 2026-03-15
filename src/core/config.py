import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Centralised application configuration loaded from environment variables."""

    # HuggingFace
    HUGGING_FACE_API_KEY: str = os.getenv("HUGGING_FACE_API_KEY", "")
    HUGGING_FACE_API_URL: str = os.getenv("HUGGING_FACE_API_URL", "https://router.huggingface.co/v1")

    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Ollama
    OLLAMA_API_URL: str = os.getenv("OLLAMA_API_URL", "http://localhost:11434/v1")

    # GitHub
    GITHUB_ACCESS_TOKEN: str = os.getenv("GITHUB_ACCESS_TOKEN", "")

    # Default provider / model
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "moonshotai/Kimi-K2-Instruct")
    DEFAULT_PROVIDER: str = os.getenv("DEFAULT_PROVIDER", "huggingface")

    # Neo4j
    NEO4J_URI: str = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "")

    # Knowledge Graph
    ENABLE_GRAPH_ENRICHMENT: bool = os.getenv("ENABLE_GRAPH_ENRICHMENT", "false").lower() == "true"
    GRAPH_QUERY_TIMEOUT: int = int(os.getenv("GRAPH_QUERY_TIMEOUT", "5"))
    MAX_IMPACT_WARNINGS: int = int(os.getenv("MAX_IMPACT_WARNINGS", "10"))

    @classmethod
    def get_model_config(cls) -> tuple[str, str, str]:
        """Returns (model_id, base_url, api_key) for the configured DEFAULT_PROVIDER."""
        provider = cls.DEFAULT_PROVIDER.lower()
        if provider == "openai":
            return cls.DEFAULT_MODEL, "https://api.openai.com/v1", cls.OPENAI_API_KEY
        if provider == "ollama":
            return cls.DEFAULT_MODEL, cls.OLLAMA_API_URL, "ollama"
        # Default: huggingface
        return cls.DEFAULT_MODEL, cls.HUGGING_FACE_API_URL, cls.HUGGING_FACE_API_KEY
