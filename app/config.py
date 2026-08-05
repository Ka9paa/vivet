from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Vivet"
    database_url: str = "sqlite:///./vivet.db"
    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 720
    cookie_secure: bool = False
    owner_username: str = "dec"
    owner_password: str = "change-me"
    base_url: str = "http://127.0.0.1:8000"

    # Discord bot settings (bot may be hosted separately).
    discord_bot_token: str = ""
    discord_application_id: str = ""
    discord_public_key: str = ""
    discord_client_secret: str = ""
    discord_guild_id: str = ""
    discord_log_channel_id: str = ""

    # Discord OAuth website access roles.
    discord_owner_role_id: str = ""
    discord_auth_role_id: str = ""
    discord_redirect_uri: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def is_vercel(self) -> bool:
        return bool(os.getenv("VERCEL"))

    @property
    def effective_base_url(self) -> str:
        configured = self.base_url.strip().rstrip("/")
        if configured and configured != "http://127.0.0.1:8000":
            return configured

        production = os.getenv("VERCEL_PROJECT_PRODUCTION_URL", "").strip()
        deployment = os.getenv("VERCEL_URL", "").strip()
        if production:
            return f"https://{production}".rstrip("/")
        if deployment:
            return f"https://{deployment}".rstrip("/")
        return "http://127.0.0.1:8000"

    @property
    def effective_discord_redirect_uri(self) -> str:
        configured = self.discord_redirect_uri.strip()
        if configured:
            return configured
        return f"{self.effective_base_url}/auth/discord/callback"


settings = Settings()

# Vercel's deployment filesystem is read-only except for /tmp.
# Configure DATABASE_URL with hosted PostgreSQL for persistent production data.
if settings.is_vercel and settings.database_url.startswith("sqlite"):
    settings.database_url = "sqlite:////tmp/vivet.db"

if settings.database_url.startswith("postgres://"):
    settings.database_url = settings.database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif settings.database_url.startswith("postgresql://") and "+psycopg" not in settings.database_url:
    settings.database_url = settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1)

if settings.is_vercel:
    settings.cookie_secure = True
