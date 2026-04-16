"""Application configuration loaded from environment variables."""

from typing import Annotated
from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode
from functools import lru_cache


class Settings(BaseSettings):
    """Settings for the FastAPI relay service."""

    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Internal API key shared with Next.js
    fastapi_internal_api_key: str = ""

    # NextAuth secret — verifies legacy HS256 plugin tokens during the
    # RS256 cutover window (ADR 2026-04-15). Removable once all in-flight
    # HS256 tokens have aged out (≤ TOKEN_TTL_HOURS = 24h).
    nextauth_secret: str = ""

    # Plugin token public key (PEM, SPKI). RS256 verify-only.
    # Web holds the corresponding private key; relay never sees it.
    plugin_jwt_public_key: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # CORS — comma-separated list of allowed browser origins.
    # Starlette refuses ["*"] when allow_credentials=True, so origins must be explicit.
    # NoDecode skips pydantic-settings' default JSON parsing so the validator below can split CSV.
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
