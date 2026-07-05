"""Unified LLM client — ``live`` (cloud) or ``mock`` (local templates)."""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from backend.config import Settings, get_settings
from backend.llm.mock_chat import MockChat

ChatBackend = ChatOpenAI | MockChat


class LlmClient:
    """Thin wrapper around LangChain ChatOpenAI or local MockChat."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self.is_mock = self._settings.is_llm_mock
        if self.is_mock:
            self._chat: ChatBackend = MockChat(model=self._settings.llm_model_primary)
            self._fallback_chat: ChatBackend | None = None
            if self._settings.llm_model_fallback_effective:
                self._fallback_chat = MockChat(model=self._settings.llm_model_fallback_effective)
            return

        api_key = self._settings.require_llm_key()
        base_url = self._settings.llm_api_base_url or self._settings.openai_api_base or None
        timeout = self._settings.llm_timeout_seconds
        self._chat = self._build_live_chat(
            api_key=api_key,
            base_url=base_url,
            model=self._settings.llm_model_primary,
            timeout=timeout,
        )
        fallback_model = self._settings.llm_model_fallback_effective
        self._fallback_chat = (
            self._build_live_chat(
                api_key=api_key,
                base_url=base_url,
                model=fallback_model,
                timeout=timeout,
            )
            if fallback_model
            else None
        )

    @staticmethod
    def _build_live_chat(
        *,
        api_key: str,
        base_url: str | None,
        model: str,
        timeout: int,
    ) -> ChatOpenAI:
        return ChatOpenAI(
            api_key=SecretStr(api_key),
            base_url=base_url,
            model=model,
            timeout=timeout,
        )

    @property
    def chat(self) -> ChatBackend:
        """Primary model client (``LLM_MODEL_PRIMARY``)."""
        return self._chat

    @property
    def fallback_chat(self) -> ChatBackend | None:
        """Fallback model client (``LLM_MODEL_FALLBACK``), or None when disabled."""
        return self._fallback_chat


@lru_cache
def get_llm_client() -> LlmClient:
    return LlmClient()


def reset_llm_client_cache() -> None:
    """Clear cached client after settings change (tests / reload)."""
    get_llm_client.cache_clear()
