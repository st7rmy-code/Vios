from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SVERKA_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://sverka:sverka@localhost:5432/sverka"
    secret_key: str = "dev-secret-change-me"
    token_ttl_seconds: int = 12 * 3600

    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_access_key: str = "sverka"
    s3_secret_key: str = "sverka-secret"
    s3_bucket: str = "sverka-imports"
    storage_backend: str = "s3"  # s3 | memory (тесты)

    max_upload_bytes: int = 20 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
