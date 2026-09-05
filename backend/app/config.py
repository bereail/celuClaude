from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5"
    # Solo hace falta si tu API key es "identity-linked" (creada desde una
    # cuenta con Workspaces/Teams) -- la API la exige en ese caso y lo dice
    # explicitamente en el error 400 si falta.
    anthropic_workspace_id: str = ""

    jwt_secret: str = "insecure-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    agent_enrollment_token: str = "change-me-enrollment-token"

    database_url: str = "sqlite:///./command_center.db"

    app_user_email: str = "me@example.com"
    app_user_password_hash: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
