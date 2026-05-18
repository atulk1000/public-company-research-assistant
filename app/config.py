from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.company_universe import (
    DEFAULT_DEMO_TICKERS,
    DEFAULT_TARGET_TICKER_FILTER,
    parse_target_tickers,
)


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    openai_reasoning_effort: str = "low"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/company_assistant"
    embedding_model: str = "text-embedding-3-small"
    default_demo_tickers: str = DEFAULT_DEMO_TICKERS
    target_tickers: str = DEFAULT_TARGET_TICKER_FILTER
    sec_user_agent: str = "Public Company Research Assistant AdminContact@example.com"
    live_cache_hours: int = 24
    sec_reference_cache_hours: int = 24
    max_document_filings_per_company: int = 12

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def ticker_list(self) -> list[str]:
        return parse_target_tickers(self.target_tickers)

    @property
    def default_demo_ticker_list(self) -> list[str]:
        return parse_target_tickers(self.default_demo_tickers)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
