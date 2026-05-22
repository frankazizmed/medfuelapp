from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MEDFUEL_",
        extra="ignore",
        case_sensitive=False,
    )

    contact_email: str = "contact@example.com"
    user_agent: str = "MedFuel/0.1 (contact@example.com)"

    database_url: str = "sqlite:///./medfuel.sqlite"

    openfda_api_key: str | None = None
    ncbi_api_key: str | None = None
    uspto_api_key: str | None = None
    firecrawl_api_key: str | None = None
    firecrawl_base_url: str = "https://api.firecrawl.dev"

    http_timeout_seconds: float = 30.0
    http_max_retries: int = 4

    sec_rate_per_second: float = Field(default=8.0, description="Below SEC's 10/sec ceiling.")
    ncbi_rate_per_second: float = Field(default=2.5, description="3/sec no-key, 10/sec keyed.")
    openfda_rate_per_minute: float = Field(default=200.0, description="Below 240/min ceiling.")
    clinicaltrials_rate_per_second: float = 5.0
    ema_rate_per_second: float = 2.0
    uspto_rate_per_second: float = 2.0
    firecrawl_rate_per_second: float = 2.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
