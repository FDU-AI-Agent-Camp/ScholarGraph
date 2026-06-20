"""Tests for the embedding client interface."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.config import Settings
from backend.llm.embeddings import EmbeddingClient


def _settings(
    *,
    provider: str = "openai",
    model: str = "bge-m3",
    api_key: str = "",
    base_url: str | None = None,
    ollama_url: str = "http://localhost:11434",
) -> Settings:
    return Settings(
        _env_file=None,
        llm_mode="mock",
        embedding_provider=provider,
        embedding_model=model,
        embedding_api_key=api_key,
        embedding_api_base_url=base_url,
        embedding_ollama_url=ollama_url,
        scholargraph_api_key="fallback-key",
        openai_api_key="",
    )


@pytest.mark.asyncio
async def test_openai_provider_calls_aembed_documents() -> None:
    settings = _settings(provider="openai", api_key="test-key", base_url="https://api.example.com/v1")
    client = EmbeddingClient(settings)

    mock_instance = MagicMock()
    mock_instance.aembed_documents = AsyncMock(return_value=[[0.1, 0.2], [0.3, 0.4]])

    with patch("backend.llm.embeddings.OpenAIEmbeddings", return_value=mock_instance) as mock_cls:
        result = await client.embed_texts(["hello", "world"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    mock_cls.assert_called_once_with(
        api_key="test-key",
        base_url="https://api.example.com/v1",
        model="bge-m3",
    )
    mock_instance.aembed_documents.assert_awaited_once_with(["hello", "world"])


@pytest.mark.asyncio
async def test_openai_provider_uses_llm_key_as_fallback() -> None:
    settings = Settings(
        _env_file=None,
        llm_mode="live",
        scholargraph_api_key="fallback-key",
        embedding_api_key="",
        embedding_provider="openai",
        embedding_model="bge-m3",
    )
    client = EmbeddingClient(settings)

    mock_instance = MagicMock()
    mock_instance.aembed_documents = AsyncMock(return_value=[])

    with patch("backend.llm.embeddings.OpenAIEmbeddings", return_value=mock_instance) as mock_cls:
        await client.embed_texts(["x"])

    assert mock_cls.call_args.kwargs["api_key"] == "fallback-key"


@pytest.mark.asyncio
async def test_ollama_provider_calls_api_embed() -> None:
    settings = _settings(provider="ollama", model="nomic-embed-text:latest", ollama_url="http://ollama:11434")
    client = EmbeddingClient(settings)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}

    mock_post = AsyncMock(return_value=mock_response)
    mock_client = MagicMock()
    mock_client.post = mock_post

    mock_async_client = MagicMock()
    mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_async_client.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("backend.llm.embeddings.httpx.AsyncClient", mock_async_client):
        result = await client.embed_texts(["hello", "world"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    mock_post.assert_awaited_once()
    call_args = mock_post.call_args
    assert call_args.args[0] == "http://ollama:11434/api/embed"
    assert call_args.kwargs["json"] == {"model": "nomic-embed-text:latest", "input": ["hello", "world"]}


@pytest.mark.asyncio
async def test_ollama_provider_batches_large_requests() -> None:
    settings = _settings(provider="ollama", model="nomic-embed-text:latest")
    client = EmbeddingClient(settings)

    texts = [f"text {i}" for i in range(40)]

    def _make_response(batch: list[str]) -> MagicMock:
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"embeddings": [[float(i), float(i + 1)] for i in range(len(batch))]}
        return response

    async def _fake_post(*args: object, **kwargs: object) -> MagicMock:
        batch = kwargs["json"]["input"]
        return _make_response(batch)

    mock_post = AsyncMock(side_effect=_fake_post)
    mock_client = MagicMock()
    mock_client.post = mock_post

    mock_async_client = MagicMock()
    mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_async_client.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("backend.llm.embeddings.httpx.AsyncClient", mock_async_client):
        result = await client.embed_texts(texts)

    assert len(result) == 40
    assert mock_post.await_count == 2
    first_batch = mock_post.await_args_list[0].kwargs["json"]["input"]
    second_batch = mock_post.await_args_list[1].kwargs["json"]["input"]
    assert len(first_batch) == 32
    assert len(second_batch) == 8


@pytest.mark.asyncio
async def test_ollama_provider_raises_on_http_error() -> None:
    settings = _settings(provider="ollama")
    client = EmbeddingClient(settings)

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "bad request"
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "bad request",
        request=MagicMock(),
        response=mock_response,
    )

    mock_post = AsyncMock(return_value=mock_response)
    mock_client = MagicMock()
    mock_client.post = mock_post

    mock_async_client = MagicMock()
    mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_async_client.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("backend.llm.embeddings.httpx.AsyncClient", mock_async_client),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await client.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_empty_texts_returns_empty_list() -> None:
    client = EmbeddingClient(_settings(provider="openai"))
    with patch("backend.llm.embeddings.OpenAIEmbeddings") as mock_cls:
        result = await client.embed_texts([])
    assert result == []
    mock_cls.assert_not_called()
