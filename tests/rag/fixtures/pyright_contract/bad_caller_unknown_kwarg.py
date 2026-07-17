# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Pyright should fail: Protocol caller must not pass undeclared kwargs."""

from __future__ import annotations

from backend.rag.protocols import VectorStoreProtocol


async def rogue_hybrid_style_call(store: VectorStoreProtocol) -> None:
    await store.query_entities(
        "ImageNet accuracy",
        paper_id="stem-001",
        score_threshold=0.5,
    )
