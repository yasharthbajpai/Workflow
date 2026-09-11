"""Central application settings, sourced entirely from environment variables.

Nothing here is hardcoded to a specific deployment: DATABASE_URL is provided by
Render, AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION / BEDROCK_MODEL_ID
are provided by whoever owns the AWS account, and JWT_SECRET / CORS_ORIGINS are
provided per-environment.
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

    # --- AWS Bedrock ----------------------------------------------------
    # aws_access_key_id/aws_secret_access_key may be left blank to fall back
    # to boto3's default credential chain (e.g. an IAM role on Render); when
    # both are set they're passed to the client explicitly.
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    bedrock_model_id: str = ""

    # --- CORS -----------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sqlalchemy_database_uri(self) -> str:
        """Normalise any Postgres URL to the psycopg3 driver we ship.

        Local .env may still say postgresql+psycopg2://; Render/Neon often
        give postgres:// or postgresql://. requirements.txt installs
        psycopg[binary], not psycopg2, so every form is rewritten here.
        """
        url = self.database_url
        for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
