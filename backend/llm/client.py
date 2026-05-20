"""Unified OpenAI-compatible LLM client."""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from backend.config import Settings, get_settings


class LlmClient:
    """Thin wrapper around LangChain ChatOpenAI for team-wide reuse."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        api_key = self._settings.require_llm_key()
        base_url = self._settings.llm_api_base_url or self._settings.openai_api_base or None
        self._chat = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=self._settings.llm_model,
            timeout=self._settings.llm_timeout_seconds,
        )

    @property
    def chat(self) -> ChatOpenAI:
        return self._chat


@lru_cache
def get_llm_client() -> LlmClient:
    return LlmClient()
