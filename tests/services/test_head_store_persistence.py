"""HeadStore persistence (P10 / P11)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.head_store import HeadStore
from backend.schemas.ingest_head import IngestHead
from backend.schemas.paper import PaperDetail, PaperStatus
from backend.services.paper_service import PaperService, get_paper_service


def test_head_store_round_trip(tmp_path: Path) -> None:
    store = HeadStore(base_dir=tmp_path)
    merged = IngestHead(
        title="MinerU Title",
        abstract="Better abstract",
        sources={"title": "mineru", "abstract": "mineru"},
    )

    store.save(
        "paper-1",
        merged=merged,
        classifier_input="Title: MinerU Title\nAbstract: Better abstract",
        warnings=["mineru_unavailable"],
    )

    record = store.load("paper-1")

    assert record is not None
    assert record.paper_id == "paper-1"
    assert record.merged.title == "MinerU Title"
    assert record.merged.sources["title"] == "mineru"
    assert record.warnings == ["mineru_unavailable"]


def test_head_store_load_missing_returns_none(tmp_path: Path) -> None:
    assert HeadStore(base_dir=tmp_path).load("missing") is None


@pytest.mark.asyncio
async def test_apply_head_refine_persists_to_disk(
    registered_paper: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_paper_service.cache_clear()  # type: ignore[attr-defined]

    merged = IngestHead(
        title="Saved Title",
        abstract="Saved abstract",
        sources={"title": "mineru", "abstract": "pymupdf"},
    )
    get_paper_service().apply_head_refine(
        registered_paper,
        merged=merged,
        classifier_input="Title: Saved Title",
        warnings=["mineru_unavailable"],
    )

    record = HeadStore(base_dir=tmp_path).load(registered_paper)

    assert record is not None
    assert record.merged.sources["title"] == "mineru"
    assert record.warnings == ["mineru_unavailable"]


@pytest.mark.asyncio
async def test_paper_service_hydrates_refined_head_after_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paper_id = "persist-head-001"
    monkeypatch.setenv("GRAPH_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    merged = IngestHead(
        title="Persisted Title",
        abstract="Persisted abstract",
        sources={"title": "grobid", "abstract": "pymupdf"},
    )
    HeadStore(base_dir=tmp_path).save(
        paper_id,
        merged=merged,
        classifier_input="Title: Persisted Title",
        warnings=["grobid_unavailable"],
    )

    now = datetime.now(UTC)
    fresh_service = PaperService()
    fresh_service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="persist test",
        status=PaperStatus.PENDING,
        created_at=now,
        updated_at=now,
    )

    detail = await fresh_service.get_paper(paper_id)

    assert detail.ingest_head is not None
    assert detail.ingest_head.title == "Persisted Title"
    assert detail.ingest_head.sources["title"] == "grobid"
    assert fresh_service.get_refined_classifier_input(paper_id) == "Title: Persisted Title"
    status = await fresh_service.get_status(paper_id)
    assert status.head_refine_warnings == ["grobid_unavailable"]

    get_settings.cache_clear()
    get_paper_service.cache_clear()  # type: ignore[attr-defined]
