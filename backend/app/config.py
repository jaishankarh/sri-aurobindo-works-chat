"""Application configuration via environment variables."""

from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    APP_NAME: str = "Sri Aurobindo RAG"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://rag:ragpassword@localhost:5432/rag_db"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_STREAM_KEY: str = "rag:stream:{message_id}"
    REDIS_SESSION_TTL: int = 86400  # 24 hours

    # Neo4j (knowledge graph store — entities/relations, multi-hop traversal)
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "aurobindo_graph"

    # Prefect
    PREFECT_API_URL: str = "http://localhost:4200/api"

    # Embedding model
    # "bge_m3"       = local BAAI/bge-m3 (dense + sparse, free, CPU/GPU).
    # "bge_m3_cloud" = the *same* bge-m3 model hosted by a third-party inference
    #     provider (DeepInfra, Together AI, Fireworks, etc.) behind an
    #     OpenAI-compatible /v1/embeddings API — configure EMBEDDING_BASE_URL +
    #     EMBEDDING_API_KEY to match your provider. Same model, same 1024-dim
    #     vector space as local "bge_m3", so switching between these two does
    #     NOT require re-ingestion. Dense only — hosted OpenAI-compatible
    #     endpoints don't expose bge-m3's sparse lexical_weights output, so the
    #     BM25 channel is skipped automatically, same as "gemini" below.
    # "gemini"       = Google's cloud embedding API (dense only, different
    #     vector space/dimension than bge-m3 — switching to/from this provider
    #     DOES require dropping the chunks table and re-ingesting).
    EMBEDDING_PROVIDER: Literal["bge_m3", "bge_m3_cloud", "gemini"] = "bge_m3"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIM: int = 1024  # must match EMBEDDING_PROVIDER's actual output dimension
    EMBEDDING_DEVICE: str = "cpu"  # "cuda" or "mps" for Apple Silicon ("bge_m3" only)
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_MAX_LENGTH: int = 8192
    EMBEDDING_BASE_URL: str = ""  # "bge_m3_cloud" only: your provider's OpenAI-compatible base URL
    EMBEDDING_API_KEY: str = ""  # "bge_m3_cloud" only

    # LLM
    LLM_PROVIDER: Literal["openai", "anthropic", "gemini", "ollama", "local"] = "ollama"
    LLM_MODEL: str = "llama3.2"
    LLM_BASE_URL: str = "http://localhost:11434"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 4096

    # Reranking
    RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"
    RERANK_TOP_K: int = 10

    # Retrieval
    DEFAULT_SIMILARITY_ALPHA: float = 0.7  # 1.0 = pure vector, 0.0 = pure keyword
    DEFAULT_TOP_K: int = 5
    GRAPH_HOP_DEPTH: int = 2

    # Parsing
    DATA_DIR: str = "./data"
    PDF_DIR: str = "./data/pdfs"
    PROCESSED_DIR: str = "./data/processed"

    # Corpus
    SRI_AUROBINDO_WRITINGS_URL: str = (
        "https://www.sriaurobindoashram.org/sriaurobindo/writings.php"
    )
    MOTHER_OEUVRES_URL: str = (
        "https://www.sriaurobindoashram.org/mother/oeuvres.php"
    )

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    @field_validator("EMBEDDING_DEVICE", mode="before")
    @classmethod
    def validate_device(cls, v: str) -> str:
        import sys
        if v == "auto":
            try:
                import torch
                if torch.cuda.is_available():
                    return "cuda"
                if sys.platform == "darwin":
                    return "mps"
            except ImportError:
                pass
            return "cpu"
        return v


settings = Settings()
