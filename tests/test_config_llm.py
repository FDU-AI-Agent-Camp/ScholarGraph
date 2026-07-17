# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Settings tests for LLM model configuration."""

from backend.config import get_settings
from backend.llm.client import LlmClient, reset_llm_client_cache


def _reset_settings() -> None:
    get_settings.cache_clear()
    reset_llm_client_cache()


def test_llm_mode_defaults_to_mock(monkeypatch) -> None:
    monkeypatch.delenv("LLM_MODE", raising=False)
    _reset_settings()
    settings = get_settings()
    assert settings.llm_mode == "mock"
    assert settings.is_llm_mock is True


def test_llm_model_primary_and_fallback(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("LLM_MODEL_PRIMARY", "DeepSeek-V3-64K")
    monkeypatch.setenv("LLM_MODEL_FALLBACK", "Qwen3-32B-64K")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    _reset_settings()
    settings = get_settings()
    assert settings.llm_model_primary == "DeepSeek-V3-64K"
    assert settings.llm_model_fallback_effective == "Qwen3-32B-64K"
    assert settings.llm_model == "DeepSeek-V3-64K"


def test_llm_model_legacy_alias(monkeypatch) -> None:
    monkeypatch.delenv("LLM_MODEL_PRIMARY", raising=False)
    monkeypatch.setenv("LLM_MODEL", "legacy-model")
    _reset_settings()
    settings = get_settings()
    assert settings.llm_model_primary == "legacy-model"


def test_llm_model_fallback_disabled_when_empty(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODEL_PRIMARY", "DeepSeek-V3-64K")
    monkeypatch.setenv("LLM_MODEL_FALLBACK", "")
    _reset_settings()
    settings = get_settings()
    assert settings.llm_model_fallback_effective is None


def test_llm_client_exposes_fallback_chat(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL_PRIMARY", "DeepSeek-V3-64K")
    monkeypatch.setenv("LLM_MODEL_FALLBACK", "Qwen3-32B-64K")
    _reset_settings()

    client = LlmClient()
    assert client.is_mock is False
    assert client.chat.model_name == "DeepSeek-V3-64K"
    assert client.fallback_chat is not None
    assert client.fallback_chat.model_name == "Qwen3-32B-64K"


def test_require_llm_key_skipped_in_mock_mode(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.delenv("SCHOLARGRAPH_API_KEY", raising=False)
    _reset_settings()
    assert get_settings().require_llm_key() == ""
