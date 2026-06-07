"""GROBID isalive probe for health endpoint (Phase C / C9)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from backend.ingest.grobid_client import check_grobid_isalive


@pytest.mark.asyncio
async def test_check_grobid_isalive_true_on_200_true_body() -> None:
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.text = "true"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.ingest.grobid_client.httpx.AsyncClient", return_value=mock_client):
        assert await check_grobid_isalive() is True


@pytest.mark.asyncio
async def test_check_grobid_isalive_false_on_connection_error() -> None:
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=OSError("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.ingest.grobid_client.httpx.AsyncClient", return_value=mock_client):
        assert await check_grobid_isalive() is False
