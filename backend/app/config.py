"""Central application settings, sourced entirely from environment variables.

Nothing here is hardcoded to a specific deployment: DATABASE_URL is provided by
Render, GEMINI_API_KEY / GEMINI_MODEL are provided by whoever owns the Gemini
project, and JWT_SECRET / CORS_ORIGINS are provided per-environment.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Database ---------------------------------------------------------
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
    db_schema: str = "Sample_test"

    # --- Auth ---------------------------------------------------------
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 12
    demo_password: str = "Nortex@123"

    # --- Gemini -------------------------------------------------------
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"

    # --- CORS -----------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sqlalchemy_database_uri(self) -> str:
        """Normalise postgres:// / postgresql:// (Render's format) to the psycopg driver."""
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://") :]
        elif url.startswith("postgresql://") and "+psycopg" not in url:
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
