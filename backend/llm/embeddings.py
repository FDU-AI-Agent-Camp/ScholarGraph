"""Lightweight embedding client for semantic graph clustering."""

from __future__ import annotations

import logging
from functools import lru_cache

import httpx
from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from backend.config import Settings, get_settings

logger = logging.getLogger(__name__)


class _OllamaEmbeddingBackend:
    """Async backend for Ollama's ``/api/embed`` endpoint."""

    def __init__(self, *, base_url: str, model: str, timeout: float = 120.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        # Ollama's /api/embed can be sensitive to very large batches; keep chunks
        # small and deterministic.
        batch_size = 32
        all_embeddings: list[list[float]] = []

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for offset in range(0, len(texts), batch_size):
                batch = texts[offset : offset + batch_size]
                response = await client.post(
                    f"{self._base_url}/api/embed",
                    json={
                        "model": self._model,
                        "input": batch,
                    },
                )
                if response.status_code >= 400:
                    logger.warning(
                        "ollama_embed_batch_failed",
                        extra={
                            "status": response.status_code,
                            "body": response.text[:500],
                            "batch_size": len(batch),
                        },
                    )
                response.raise_for_status()
                payload = response.json()
                embeddings = payload.get("embeddings")
                if not isinstance(embeddings, list) or len(embeddings) != len(batch):
                    raise ValueError(f"Unexpected Ollama embed response shape: {list(payload.keys())}")
                all_embeddings.extend(embeddings)

        return all_embeddings


class EmbeddingClient:
    """Thin wrapper around an embedding provider.

    Supports:

    - ``openai``: any OpenAI-compatible endpoint (default; Huawei Cloud MaaS
      falls into this category).
    - ``ollama``: local Ollama server, useful for offline dev / comparison.

    Defaults to the same base URL / API key as the primary LLM for the OpenAI
    provider so that cloud configuration stays minimal.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._provider = self._settings.embedding_provider
        self._ollama: _OllamaEmbeddingBackend | None = None
        self._openai: OpenAIEmbeddings | None = None

    def _openai_client(self) -> OpenAIEmbeddings:
        if self._openai is None:
            self._openai = OpenAIEmbeddings(
                api_key=SecretStr(self._settings.embedding_api_key_effective),
                base_url=self._settings.embedding_api_base_url_effective,
                model=self._settings.embedding_model,
            )
        return self._openai

    def _ollama_client(self) -> _OllamaEmbeddingBackend:
        if self._ollama is None:
            self._ollama = _OllamaEmbeddingBackend(
                base_url=self._settings.embedding_ollama_url,
                model=self._settings.embedding_model,
            )
        return self._ollama

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text.

        Empty strings are embedded as zero vectors so callers can keep indices
        stable without additional branching.
        """
        if not texts:
            return []

        normalized = [text if text else "" for text in texts]
        logger.debug("embedding_request", extra={"provider": self._provider, "texts": len(normalized)})

        if self._provider == "ollama":
            vectors = await self._ollama_client().embed_texts(normalized)
        else:
            vectors = await self._openai_client().aembed_documents(normalized)

        logger.debug("embedding_response", extra={"vectors": len(vectors)})
        return vectors


@lru_cache
def get_embedding_client() -> EmbeddingClient:
    return EmbeddingClient()


def reset_embedding_client_cache() -> None:
    """Clear cached client after settings change (tests / reload)."""
    get_embedding_client.cache_clear()
