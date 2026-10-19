"""Settings read from environment variables (and `.env` in development).

Every setting is listed in `.env.example` at the repository root. Secrets have no default.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from sabq import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database (psycopg 3 driver, used for both sync and async engines)
    database_url: str = "postgresql+psycopg://sabq:sabq@localhost:5432/sabq"

    # General
    log_level: str = "INFO"
    public_base_url: str = "http://localhost"

    # Bot identity: contact URL is optional until production (decision 2026-10-19)
    sabqbot_contact_url: str = ""

    # Egress for geo-blocked .dz sources
    dz_proxy_url: str = ""

    # Story-matching embeddings (OpenRouter, OpenAI-compatible)
    openrouter_api_key: SecretStr | None = None
    embedding_model: str = "voyageai/voyage-4"
    embedding_base_url: str = "https://openrouter.ai/api/v1"

    # Transactional email (MailerSend over SMTP; Mailpit in development)
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: SecretStr | None = None
    email_from: str = "Sabq <no-reply@localhost>"

    # Worker
    worker_heartbeat_file: str = "/tmp/sabq-worker-heartbeat"
    worker_tick_seconds: float = 5.0

    @property
    def user_agent(self) -> str:
        agent = f"SabqBot/{__version__}"
        if self.sabqbot_contact_url:
            agent += f" (+{self.sabqbot_contact_url})"
        return agent


@lru_cache
def get_settings() -> Settings:
    return Settings()
