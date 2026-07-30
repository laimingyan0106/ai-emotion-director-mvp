from functools import lru_cache
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    llm_api_key: str | None = None
    image_api_key: str | None = None
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
