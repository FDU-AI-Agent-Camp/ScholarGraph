"""Extended persistence smoke tests (SMK-06~08)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.smoke
def test_smoke_pipeline_finalized_importable() -> None:
    from backend.events.types import EventType, PipelineFinalized

    assert EventType.PIPELINE_FINALIZED.value == "pipeline_finalized"
    assert "paper_id" in PipelineFinalized.__dataclass_fields__


@pytest.mark.smoke
def test_smoke_to_async_database_url_callable() -> None:
    from backend.db.url import to_async_database_url

    assert "aiosqlite" in to_async_database_url("sqlite:///./data/x.db")


@pytest.mark.smoke
def test_smoke_pyproject_lists_persistence_dependencies() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "sqlalchemy" in text
    assert "aiosqlite" in text
    assert "alembic" in text
