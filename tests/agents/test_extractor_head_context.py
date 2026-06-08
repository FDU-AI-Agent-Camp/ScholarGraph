"""Unit tests: ``_resolve_head_context`` (F.2.1 X6)."""

from __future__ import annotations

import pytest
from backend.agents.extractor import _resolve_head_context
from backend.config import get_settings
from backend.graph.head_store import HeadStore
from backend.schemas.ingest_head import IngestHead


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


def test_resolve_head_context_prefers_in_memory_refined_head(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime

    from backend.schemas.paper import PaperDetail, PaperStatus
    from backend.services.paper_service import get_paper_service

    paper_id = "head-memory-priority"
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    now = datetime.now(UTC)
    get_paper_service()._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="t",
        status=PaperStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    HeadStore(base_dir=tmp_path).save(
        paper_id,
        merged=IngestHead(title="Disk Title", abstract="disk"),
        classifier_input="Title: Disk Title",
    )
    get_paper_service().apply_head_refine(
        paper_id,
        merged=IngestHead(title="Memory Title", abstract="memory abstract"),
        classifier_input="Title: Memory Title",
        warnings=[],
    )

    context = _resolve_head_context(paper_id)

    assert context is not None
    assert "Memory Title" in context
    assert "memory abstract" in context
    assert "Disk Title" not in context

    get_settings.cache_clear()
