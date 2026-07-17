# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests: ``_resolve_head_context`` (F.2.1 X6)."""

from __future__ import annotations

import pytest
from backend.agents.extractor import _resolve_head_context
from backend.config import get_settings
from backend.graph.head_store import HeadStore
from backend.schemas.ingest_head import IngestHead
from backend.services.paper_service import get_paper_service


def test_resolve_head_context_returns_none_when_no_head(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    assert _resolve_head_context("no-such-paper") is None

    get_settings.cache_clear()


def test_resolve_head_context_reads_from_head_store(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    paper_id = "head-store-only"
    HeadStore(base_dir=tmp_path).save(
        paper_id,
        merged=IngestHead(title="Disk Title", abstract="Disk abstract", intro="Intro snippet"),
        classifier_input="Title: Disk Title",
    )

    context = _resolve_head_context(paper_id)

    assert context is not None
    assert "Disk Title" in context
    assert "Disk abstract" in context
    assert "Intro snippet" in context

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_resolve_head_context_uses_head_store_after_apply_refine(
    persistence_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.schemas.paper import PaperStatus
    from tests.helpers.persistence_testkit import register_test_paper

    paper_id = "head-store-priority"
    graph_dir = persistence_env["graph_dir"]
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()
    get_paper_service.cache_clear()

    await register_test_paper(paper_id, status=PaperStatus.PENDING)
    HeadStore(base_dir=graph_dir).save(
        paper_id,
        merged=IngestHead(title="Disk Title", abstract="disk"),
        classifier_input="Title: Disk Title",
    )
    get_paper_service().apply_head_refine(
        paper_id,
        merged=IngestHead(title="Refined Title", abstract="refined abstract"),
        classifier_input="Title: Refined Title",
        warnings=[],
    )

    context = _resolve_head_context(paper_id)

    assert context is not None
    assert "Refined Title" in context
    assert "refined abstract" in context
    assert "Disk Title" not in context

    get_settings.cache_clear()
    get_paper_service.cache_clear()
