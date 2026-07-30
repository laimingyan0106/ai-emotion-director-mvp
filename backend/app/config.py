from functools import lru_cache
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    app_name: str = "AI Emotion Director API"
    database_url: str = "postgresql://emotion:emotion@localhost:5432/emotion_director"
    media_root: Path = Path("./media")
    media_storage_mode: str = "auto"
    cors_origins: str = "http://localhost:3000"
    cors_origin_regex: str = r"https://.*\.(?:chatgpt\.site|vercel\.app)"
    storage_mode: str = "auto"
    sqlite_path: Path = Path("./.data/emotion-director.db")
    adapter_mode: str = "demo"
    generation_retry_attempts: int = Field(default=1, ge=0, le=3)
    audio_analysis_timeout_seconds: int = Field(default=45, ge=5, le=300)
    audio_analysis_max_seconds: int = Field(default=600, ge=30, le=3600)
    llm_api_key: str | None = None
    llm_provider: str = "openai"
    llm_model: str = "gpt-5.6-terra"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_style: str = "responses"
    llm_timeout_seconds: int = Field(default=60, ge=5, le=300)
    llm_http_retries: int = Field(default=2, ge=0, le=5)
    image_api_key: str | None = None
    image_adapter_mode: str = "auto"
    image_model: str = "gpt-image-2"
    image_base_url: str | None = None
    image_quality: str = "medium"
    image_size: str = "1280x720"
    image_timeout_seconds: int = Field(default=150, ge=10, le=300)
    video_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def allowed_origins(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]

    @property
    def resolved_storage_mode(self) -> str:
        if self.storage_mode != "auto":
            return self.storage_mode
        if os.getenv("DATABASE_URL"):
            return "postgres"
        return "sqlite" if os.getenv("VERCEL") else "postgres"

    @property
    def resolved_media_root(self) -> Path:
        if os.getenv("VERCEL") and self.media_root == Path("./media"):
            return Path("/tmp/emotion-director-media")
        return self.media_root

    @property
    def resolved_media_storage_mode(self) -> str:
        if self.media_storage_mode != "auto":
            return self.media_storage_mode
        return "vercel_blob" if os.getenv("BLOB_READ_WRITE_TOKEN") else "local"

    @property
    def resolved_sqlite_path(self) -> Path:
        if os.getenv("VERCEL") and self.sqlite_path == Path("./.data/emotion-director.db"):
            return Path("/tmp/emotion-director.db")
        return self.sqlite_path

    @property
    def resolved_llm_api_key(self) -> str | None:
        return self.llm_api_key or os.getenv("OPENAI_API_KEY")

    @property
    def resolved_image_api_key(self) -> str | None:
        return self.image_api_key or os.getenv("OPENAI_API_KEY") or self.resolved_llm_api_key

    @property
    def resolved_image_base_url(self) -> str:
        return (self.image_base_url or self.llm_base_url).rstrip("/")

    @property
    def resolved_image_adapter_mode(self) -> str:
        if self.image_adapter_mode != "auto":
            return self.image_adapter_mode
        return self.adapter_mode


@lru_cache
def get_settings() -> Settings:
    return Settings()
