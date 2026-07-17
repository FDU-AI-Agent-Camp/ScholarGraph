# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Extended authorization tests (AUTH-07, AUTH-10)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from tests.api.conftest import assert_error_envelope

VALID_PDF = b"%PDF-1.4\n% authz extended"


@pytest.mark.asyncio
async def test_reextract_foreign_paper_returns_404(
    api_client: AsyncClient,
    persistence_env,
) -> None:
    response = await api_client.post("/api/v1/papers/foreign-reextract/reextract")
    assert response.status_code == 404
    assert_error_envelope(response.json(), code="PAPER_NOT_FOUND")


@pytest.mark.asyncio
async def test_very_long_paper_id_returns_404_not_500(
    api_client: AsyncClient,
    persistence_env,
) -> None:
    long_id = "x" * 256
    response = await api_client.get(f"/api/v1/papers/{long_id}")
    assert response.status_code == 404
    assert_error_envelope(response.json(), code="PAPER_NOT_FOUND")
