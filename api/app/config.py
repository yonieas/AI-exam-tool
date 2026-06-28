"""Application configuration (12-factor)."""
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://examtool:examtool@localhost:5432/examtool"

    # Redis (sessions + future queue)
    redis_url: str = "redis://localhost:6379/0"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "examtool"
    minio_secret_key: str = "examtool123"
    minio_bucket: str = "examtool"
    minio_public_base_url: str = "http://localhost:9000"

    # Auth
    secret_key: str = "dev-secret"
    jwt_signing_key: str = "dev-jwt-signing-key"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 2_592_000
    cookie_domain: str = "localhost"
    cookie_secure: bool = False
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    dev_login_enabled: bool = True  # dev-only email login

    # AI
    ai_provider: Literal["minimax", "mock", "anthropic"] = "mock"
    ai_provider_policy: str = "single_provider"  # 'single_provider' | 'cascade_with_fallback'
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimax.io/v1"
    minimax_model: str = "MiniMax-M2.7"
    minimax_cheap_model: str = "MiniMax-M2.7"

    # Frontend
    api_base_url: str = "http://localhost:8000"
    next_public_api_base_url: str = "http://localhost:8000"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
