from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from app.config import get_settings


class OpenAIConfigurationError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    settings = get_settings()
    if not settings.openai_api_key:
        raise OpenAIConfigurationError(
            "OPENAI_API_KEY is not configured. Set it in your environment or .env before running LLM-backed analysis."
        )
    return OpenAI(api_key=settings.openai_api_key)

