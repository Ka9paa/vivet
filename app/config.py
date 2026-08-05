from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Vivet"
    database_url: str = "sqlite:///./vivet.db"
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 720
    cookie_secure: bool = False
    owner_username: str = "dec"
    owner_password: str = "dec11"
    base_url: str = "http://127.0.0.1:8000"
    discord_bot_token: str = ""
    discord_application_id: str = ""
    discord_public_key: str = ""
    discord_client_secret: str = ""
    discord_guild_id: str = ""
    discord_owner_user_id: str = ""
    discord_auth_staff_role_id: str = ""
    discord_log_channel_id: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
