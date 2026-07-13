"""Extended PaperRepository unit tests (test design U-PR-05~07)."""

from __future__ import annotations

import pytest
from backend.repositories.paper_repository import PaperRepository
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm, ParadigmClassification


@pytest.mark.asyncio
async def test_mark_preview_available_sets_flag(persistence_env) -> None:
    repo = PaperRepository()
    await repo.create("preview-001", "Preview", "/tmp/p.pdf")
    await repo.mark_preview_available("preview-001")
    loaded = await repo.get("preview-001")
    assert loaded is not None
    assert loaded.preview_available is True


@pytest.mark.asyncio
async def test_update_classification_sets_paradigm(persistence_env) -> None:
    repo = PaperRepository()
    await repo.create("cls-001", "Classify", "/tmp/c.pdf", status=PaperStatus.PENDING)
    classification = ParadigmClassification(
        paradigm=Paradigm.STEM,
        confidence=0.95,
        reason="unit",
    )
    await repo.update_classification("cls-001", classification)
    loaded = await repo.get("cls-001")
    assert loaded is not None
    assert loaded.paradigm == Paradigm.STEM
    assert loaded.classification == classification


@pytest.mark.asyncio
async def test_delete_removes_paper_row(persistence_env) -> None:
    repo = PaperRepository()
    await repo.create("del-001", "Delete", "/tmp/d.pdf")
    assert await repo.delete("del-001") is True
    assert await repo.get("del-001") is None
    assert await repo.delete("del-001") is False
