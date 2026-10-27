"""Environment-based configuration. Secrets are read from the server environment only."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = "Smart AI Hiring Assistant"
    full_title: str = "Smart AI Hiring Assistant Using Multi-Agent LLMs and Retrieval-Augmented Generation"
    environment: str = field(default_factory=lambda: os.environ.get("APP_ENV", "development"))
    database_url: str = field(default_factory=lambda: os.environ.get("DATABASE_URL", "sqlite:///./data/saiha.db"))
    jwt_secret: str = field(default_factory=lambda: os.environ.get("JWT_SECRET", ""))
    jwt_ttl_minutes: int = field(default_factory=lambda: int(os.environ.get("JWT_TTL_MINUTES", "480")))
    cors_origins: tuple[str, ...] = field(default_factory=lambda: tuple(
        o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()))
    storage_dir: str = field(default_factory=lambda: os.environ.get("STORAGE_DIR", "./data/files"))
    dataset_dir: str = field(default_factory=lambda: os.environ.get("DATASET_DIR", "./data/datasets"))
    max_upload_mb: int = field(default_factory=lambda: int(os.environ.get("MAX_UPLOAD_MB", "10")))
    enable_ocr: bool = field(default_factory=lambda: _bool("ENABLE_OCR", True))
    # retrieval models
    embedding_model: str = field(default_factory=lambda: os.environ.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
    cross_encoder_model: str = field(default_factory=lambda: os.environ.get("CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"))
    chroma_dir: str = field(default_factory=lambda: os.environ.get("CHROMA_DIR", "./data/chroma"))
    chroma_host: str = field(default_factory=lambda: os.environ.get("CHROMA_HOST", ""))
    chroma_port: int = field(default_factory=lambda: int(os.environ.get("CHROMA_PORT", "8000")))
    enable_dense: bool = field(default_factory=lambda: _bool("ENABLE_DENSE", True))
    enable_rerank: bool = field(default_factory=lambda: _bool("ENABLE_RERANK", True))
    # LLM providers
    llm_provider: str = field(default_factory=lambda: os.environ.get("LLM_PROVIDER", "none"))
    llm_model: str = field(default_factory=lambda: os.environ.get("LLM_MODEL", ""))
    llm_fallback_provider: str = field(default_factory=lambda: os.environ.get("LLM_FALLBACK_PROVIDER", "none"))
    llm_fallback_model: str = field(default_factory=lambda: os.environ.get("LLM_FALLBACK_MODEL", ""))
    openai_api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    openai_base_url: str = field(default_factory=lambda: os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    ollama_base_url: str = field(default_factory=lambda: os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    llm_timeout_s: float = field(default_factory=lambda: float(os.environ.get("LLM_TIMEOUT_S", "60")))
    llm_price_in_per_mtok: float = field(default_factory=lambda: float(os.environ.get("LLM_PRICE_INPUT_PER_MTOK", "0")))
    llm_price_out_per_mtok: float = field(default_factory=lambda: float(os.environ.get("LLM_PRICE_OUTPUT_PER_MTOK", "0")))
    # dataset
    hf_dataset_repo: str = field(default_factory=lambda: os.environ.get("HF_DATASET_REPO", "michaelozon/candidate-matching-synthetic"))
    hf_token: str = field(default_factory=lambda: os.environ.get("HF_TOKEN", ""))
    # security
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.environ.get("RATE_LIMIT_PER_MINUTE", "240")))
    login_rate_limit_per_minute: int = field(default_factory=lambda: int(os.environ.get("LOGIN_RATE_LIMIT_PER_MINUTE", "10")))
    bootstrap_admin_email: str = field(default_factory=lambda: os.environ.get("BOOTSTRAP_ADMIN_EMAIL", ""))
    bootstrap_admin_password: str = field(default_factory=lambda: os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", ""))
    coverage_threshold: float = field(default_factory=lambda: float(os.environ.get("COVERAGE_THRESHOLD", "0.5")))

    def validate(self) -> list[str]:
        problems = []
        if len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be set to at least 32 random characters.")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
