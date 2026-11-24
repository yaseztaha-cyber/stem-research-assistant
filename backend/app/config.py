import os
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR.parent / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
DB_PATH = STORAGE_DIR / "app.db"

class Settings(BaseSettings):
    app_name: str = "AI STEM Research Assistant"
    app_version: str = "0.2.0"
    debug: bool = True
    secret_key: str = "dev-secret-key-change-in-production-please-override"
    database_url: str = f"sqlite:///{DB_PATH}"
    upload_dir: Path = UPLOAD_DIR
    max_upload_size_mb: int = 50
    allowed_extensions: set = {".pdf", ".txt", ".md", ".csv", ".markdown"}
    # Model abstraction
    llm_provider: str = "mock"  # mock | real | local | openai (openai = legacy alias of real)
    embedding_provider: str = "tfidf"  # tfidf | openai | dense | sentence_transformer
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    dense_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    # Real LLM (v0.5): OpenAI-compatible HTTP endpoint (OpenAI, Ollama, vLLM, ...)
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_fallback_to_mock: bool = False  # explicit opt-in only (v0.5 integrity)
    # Local HF LLM (v0.5): real on-device generator, no API key
    llm_hf_model: str = "HuggingFaceTB/SmolLM2-135M-Instruct"
    llm_hf_max_new_tokens: int = 150
    # Deterministic generation settings (recorded per benchmark run)
    llm_temperature: float = 0.2
    llm_top_p: float = 1.0
    llm_max_tokens: int = 1200
    answer_prompt_version: str = "v3"  # v1 | v2 | v3 (see backend/app/prompts/)
    # Retrieval v0.2
    retrieval_top_k: int = 8
    hybrid_vector_weight: float = 0.6
    hybrid_keyword_weight: float = 0.4
    semantic_weight: float = 0.6  # alias, v0.2 naming
    keyword_weight: float = 0.4
    top_k_retrieval: int = 30  # candidates before rerank
    top_k_rerank: int = 8  # final evidence
    min_relevance_score: float = 0.08
    mmr_lambda: float = 0.7  # relevance vs diversity trade-off (0-1)
    reranker_provider: str = "simple"  # simple | cross_encoder
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    grounding_threshold: float = 0.6
    citation_threshold: float = 0.5
    enable_retrieval_trace: bool = True
    document_parser: str = "layout_aware"  # pypdf | layout_aware
    equation_parser: str = "advanced"  # regex | advanced
    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    class Config:
        env_file = ".env"
        extra = "ignore"

@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    # ensure dirs
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return s

settings = get_settings()
