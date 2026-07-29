from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Emotion Director API"
    database_url: str = "postgresql://emotion:emotion@localhost:5432/emotion_director"
    media_root: Path = Path("./media")
    cors_origins: str = "http://localhost:3000"
    adapter_mode: str = "demo"
    llm_api_key: str | None = None
    image_api_key: str | None = None
    video_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def allowed_origins(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
