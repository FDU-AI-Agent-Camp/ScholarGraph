"""Tests for QA Generator vs Judge role-based LLM client isolation."""

from __future__ import annotations

import pytest

from backend.config import get_settings
from backend.llm.client import get_judge_llm_client, get_qa_llm_client, reset_llm_client_cache
from backend.llm.roles import LlmRole, clients_are_isolated, resolve_llm_binding


@pytest.fixture(autouse=True)
def _reset_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_llm_client_cache()
    yield
    get_settings.cache_clear()
    reset_llm_client_cache()


def test_resolve_qa_binding_uses_dedicated_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL_QA", "qa-fast-model")
    monkeypatch.setenv("LLM_MODEL_PRIMARY", "primary-model")
    get_settings.cache_clear()

    binding = resolve_llm_binding(get_settings(), LlmRole.QA)
    assert binding.model == "qa-fast-model"
    assert binding.enable_fallback is False


def test_resolve_judge_binding_uses_dedicated_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL_JUDGE", "judge-strong-model")
    monkeypatch.setenv("JUDGE_API_KEY", "judge-secret-key")
    monkeypatch.setenv("JUDGE_API_BASE_URL", "https://judge.example/v1")
    get_settings.cache_clear()

    binding = resolve_llm_binding(get_settings(), LlmRole.JUDGE)
    assert binding.model == "judge-strong-model"
    assert binding.api_key == "judge-secret-key"
    assert binding.base_url == "https://judge.example/v1"


def test_qa_and_judge_clients_isolated_when_models_differ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL_QA", "qa-generator")
    monkeypatch.setenv("LLM_MODEL_JUDGE", "judge-evaluator")
    get_settings.cache_clear()
    reset_llm_client_cache()

    qa_client = get_qa_llm_client()
    judge_client = get_judge_llm_client()

    assert qa_client.role is LlmRole.QA
    assert judge_client.role is LlmRole.JUDGE
    assert clients_are_isolated(qa_client, judge_client)


def test_qa_and_judge_clients_share_fingerprint_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL_PRIMARY", "shared-model")
    get_settings.cache_clear()
    reset_llm_client_cache()

    qa_client = get_qa_llm_client()
    judge_client = get_judge_llm_client()

    assert not clients_are_isolated(qa_client, judge_client)
