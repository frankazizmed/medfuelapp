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
    # IP Intelligence Engine. EPO bearer token enables the EPO adapter;
    # without it the EPO adapter is a no-op and US-only IP coverage remains.
    epo_api_key: str | None = None

    # LLM routing. Off by default so CI and local dev run with the deterministic
    # stubs. Set MEDFUEL_USE_LLM=1 plus the relevant key to enable real calls.
    use_llm: bool = False
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    extraction_model: str = Field(
        default="gpt-5.4-mini",
        description="OpenAI model used for structured extraction. Override via env if your "
        "deployment exposes an internal alias (for example a 'GPT-5.5 mini' alias).",
    )
    extraction_adjudicator_model: str = "gpt-5.5"
    narrative_model: str = "claude-opus-4-7"
    narrative_fallback_model: str = "claude-sonnet-4-6"

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
