from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All env vars are namespaced CE_* so the island never collides with the host."""

    model_config = SettingsConfigDict(env_prefix="CE_", env_file=".env", extra="ignore")

    openai_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")
    tavily_api_key: str = Field(default="")
    firecrawl_api_key: str = Field(default="")
    ncbi_api_key: str = Field(default="")
    database_url: str = Field(default="postgresql+asyncpg://postgres:postgres@localhost:5432/medfuel")
    sec_user_agent: str = Field(default="MedFuel Clinical Evidence Engine contact@medfuel.example")

    extraction_model: str = Field(default="gpt-5.5-mini")
    narrative_model: str = Field(default="claude-opus-4-7")
    narrative_fallback_model: str = Field(default="claude-sonnet-4-6")
    embedding_model: str = Field(default="text-embedding-3-large")
    embedding_dim: int = Field(default=3072)

    default_page_target: int = Field(default=6)
    max_page_target: int = Field(default=10)
    expansion_threshold: float = Field(default=0.10)

    request_timeout_s: int = Field(default=30)
    max_concurrent_fetches: int = Field(default=8)


@lru_cache
def get_settings() -> Settings:
    return Settings()
