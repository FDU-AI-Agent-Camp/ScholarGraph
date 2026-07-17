# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unified LLM client — ``live`` (cloud) or ``mock`` (local templates).

Supports role-based bindings so QA Generator and Judge evaluators can use
independent models, API keys, and endpoints (rate-limit isolation).
"""

from __future__ import annotations

from functools import lru_cache
from hashlib import sha256

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from backend.config import Settings, get_settings
from backend.llm.mock_chat import MockChat
from backend.llm.roles import LlmBinding, LlmRole, resolve_llm_binding

ChatBackend = ChatOpenAI | MockChat


class LlmClient:
    """Thin wrapper around LangChain ChatOpenAI or local MockChat."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        role: LlmRole = LlmRole.DEFAULT,
        binding: LlmBinding | None = None,
        # Legacy kwargs — prefer ``role`` / dedicated factory functions.
        model: str | None = None,
        timeout_seconds: int | None = None,
        enable_fallback: bool | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self.is_mock = self._settings.is_llm_mock

        if binding is not None:
            resolved = binding
        elif any(value is not None for value in (model, timeout_seconds, enable_fallback, api_key, base_url)):
            resolved = LlmBinding(
                role=role,
                model=model or self._settings.llm_model_primary,
                api_key=api_key if api_key is not None else self._settings.require_llm_key(),
                base_url=base_url if base_url is not None else self._settings.llm_api_base_url,
                timeout_seconds=timeout_seconds or self._settings.llm_timeout_seconds,
                enable_fallback=enable_fallback if enable_fallback is not None else True,
            )
        else:
            resolved = resolve_llm_binding(self._settings, role)

        self._role = resolved.role
        self._model = resolved.model
        self._api_key = resolved.api_key
        self._base_url = resolved.base_url
        self._timeout = resolved.timeout_seconds
        self._enable_fallback = resolved.enable_fallback

        if self.is_mock:
            self._chat: ChatBackend = MockChat(model=self._model)
            self._fallback_chat: ChatBackend | None = None
            if self._enable_fallback and self._settings.llm_model_fallback_effective:
                self._fallback_chat = MockChat(model=self._settings.llm_model_fallback_effective)
            return

        self._chat = self._build_live_chat(
            api_key=self._api_key,
            base_url=self._base_url,
            model=self._model,
            timeout=self._timeout,
        )
        fallback_model = self._settings.llm_model_fallback_effective if self._enable_fallback else None
        self._fallback_chat = (
            self._build_live_chat(
                api_key=self._api_key,
                base_url=self._base_url,
                model=fallback_model,
                timeout=self._timeout,
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
    def role(self) -> LlmRole:
        return self._role

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def api_base_url(self) -> str | None:
        return self._base_url

    @property
    def identity_fingerprint(self) -> tuple[str, str | None, str]:
        """Opaque tuple for checking Generator/Judge isolation."""
        if self.is_mock:
            key_fp = "mock"
        elif not self._api_key:
            key_fp = "empty"
        else:
            key_fp = sha256(self._api_key.encode()).hexdigest()[:12]
        return (self._model, self._base_url, key_fp)

    @property
    def chat(self) -> ChatBackend:
        """Primary chat backend for this role binding."""
        return self._chat

    @property
    def fallback_chat(self) -> ChatBackend | None:
        """Fallback model client, or None when disabled for this role."""
        return self._fallback_chat


@lru_cache
def get_llm_client() -> LlmClient:
    """Default LLM client (extract / classify / legacy callers)."""
    return LlmClient(role=LlmRole.DEFAULT)


@lru_cache
def get_qa_llm_client() -> LlmClient:
    """QA Generator client — SSE answer stream (``LLM_MODEL_QA``)."""
    return LlmClient(role=LlmRole.QA)


@lru_cache
def get_judge_llm_client() -> LlmClient:
    """Judge evaluator client — structured JSON verdict (``LLM_MODEL_JUDGE``)."""
    return LlmClient(role=LlmRole.JUDGE)


def reset_llm_client_cache() -> None:
    """Clear cached clients after settings change (tests / reload)."""
    get_llm_client.cache_clear()
    get_qa_llm_client.cache_clear()
    get_judge_llm_client.cache_clear()
