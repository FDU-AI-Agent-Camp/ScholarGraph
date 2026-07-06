"""Settings tests for RAG / chunking / vector retrieval configuration."""

from __future__ import annotations

import pytest
from backend.config import Settings, get_settings
from pydantic import ValidationError


def _reset_settings() -> None:
    get_settings.cache_clear()


def test_rag_chunk_defaults() -> None:
    _reset_settings()
    settings = Settings.model_validate({"embedding_provider": "openai"})

    assert settings.rag_chunk_size_chars == 1500
    assert settings.rag_chunk_overlap_ratio == 0.20
    assert settings.rag_chunk_min_chunk_chars == 200
    assert settings.rag_chunk_min_soft_boundary_window_chars == 200
    assert settings.rag_chunk_include_references is False


def test_rag_top_k_defaults() -> None:
    _reset_settings()
    settings = Settings.model_validate({"embedding_provider": "openai"})

    assert settings.rag_top_k_chunks == 5
    assert settings.rag_top_k_entities == 5
    assert settings.rag_top_k_relations == 5


def test_rag_top_k_rejects_zero_or_negative() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"embedding_provider": "openai", "rag_top_k_chunks": 0})

    with pytest.raises(ValidationError):
        Settings.model_validate({"embedding_provider": "openai", "rag_top_k_entities": -1})


def test_rag_chunk_size_has_minimum_floor() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"embedding_provider": "openai", "rag_chunk_size_chars": 100})


def test_rag_chunk_overlap_ratio_must_be_fraction() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"embedding_provider": "openai", "rag_chunk_overlap_ratio": 1.0})


def test_env_overrides_apply(monkeypatch) -> None:
    monkeypatch.setenv("RAG_CHUNK_SIZE_CHARS", "1200")
    monkeypatch.setenv("RAG_CHUNK_MIN_CHUNK_CHARS", "100")
    monkeypatch.setenv("RAG_CHUNK_INCLUDE_REFERENCES", "true")
    monkeypatch.setenv("RAG_TOP_K_CHUNKS", "7")
    _reset_settings()

    settings = get_settings()
    assert settings.rag_chunk_size_chars == 1200
    assert settings.rag_chunk_min_chunk_chars == 100
    assert settings.rag_chunk_include_references is True
    assert settings.rag_top_k_chunks == 7
