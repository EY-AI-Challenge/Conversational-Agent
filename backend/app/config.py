from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration loaded from environment variables."""

    app_name: str = "Knowledge Navigator EY Assistant"
    api_prefix: str = "/api"
    project_root: Path = Path(__file__).resolve().parents[2]
    data_dir: Path = Path(__file__).resolve().parents[2] / "Data"
    upload_dir: Path = Path(__file__).resolve().parents[2] / "Data" / "uploads"
    chroma_path: Path = Path(__file__).resolve().parents[2] / "chroma_db"
    collection_name: str = "ey_knowledge_navigator"

    google_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"
    gemini_embedding_model: str = "models/gemini-embedding-001"

    chunk_size: int = 1100
    chunk_overlap: int = 180
    retrieval_k: int = 7
    min_relevance_score: float = 0.18
    web_sources_enabled: bool = False

    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_google_api_key(self) -> str | None:
        return self.google_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
