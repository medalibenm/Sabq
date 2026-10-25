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

    # Polite fetching (docs/architecture.md, layer 1)
    fetch_timeout_s: float = 15.0
    fetch_min_host_gap_s: float = 5.0  # raised to the site's Crawl-delay when it asks for more
    fetch_gap_jitter: float = 0.2  # each gap is 0-20 % longer, never shorter
    fetch_backoff_base_s: float = 60.0  # 60 s, 120 s, 240 s ... after 429 / 5xx / network errors
    fetch_backoff_max_s: float = 3600.0
    fetch_retry_after_max_s: float = 86400.0  # a site's Retry-After is honoured up to a day
    fetch_max_bytes: int = 20_000_000
    robots_ttl_s: float = 86400.0
    robots_retry_s: float = 900.0  # robots.txt unreachable: no requests to it, retry in 15 min

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

    # Ingestion (plan M5)
    ingest_enabled: bool = True  # false: the worker only keeps its heartbeat
    ingest_concurrency: int = 4  # sources polled at the same time (one request per host still)
    ingest_jitter: float = 0.2  # each interval is 80-120 % of poll_interval_s
    ingest_max_article_pages: int = 20  # per poll, new articles only (decision 2026-10-21)
    ingest_baseline_gap_s: float = 86400.0  # no successful poll for this long: next is a baseline

    @property
    def user_agent(self) -> str:
        agent = f"SabqBot/{__version__}"
        if self.sabqbot_contact_url:
            agent += f" (+{self.sabqbot_contact_url})"
        return agent


@lru_cache
def get_settings() -> Settings:
    return Settings()
