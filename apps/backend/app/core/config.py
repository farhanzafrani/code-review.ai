from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/codereviewai"
    redis_url: str = "redis://localhost:6379/0"

    worker_metrics_port: int = 9200
    slack_webhook_url: str = ""

    github_app_id: str = ""
    github_app_client_id: str = ""
    github_app_client_secret: str = ""
    github_app_private_key_path: str = ""
    github_app_webhook_secret: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    max_diff_chars: int = 30_000

    qdrant_url: str = "http://localhost:6333"
    embedding_model: str = "text-embedding-3-small"
    rag_top_k: int = 5

    # Off by default: needs a running SonarQube instance + a token with
    # "Create Projects" permission. See README before enabling.
    sonarqube_enabled: bool = False
    sonarqube_url: str = "http://localhost:9000"
    sonarqube_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
