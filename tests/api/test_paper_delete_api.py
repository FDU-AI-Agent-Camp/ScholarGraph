"""API tests for DELETE /papers/{id} and reextract force override."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import fitz
import pytest
from backend.config import get_settings
from backend.graph.state import STAGE_PERCENT
from backend.main import app
from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.services.paper_service import get_paper_service
from httpx import ASGITransport, AsyncClient
from tests.helpers.persistence_testkit import init_isolated_database, reset_persistence_singletons


@pytest.fixture
async def api_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "delete_api.db"
    upload_path = tmp_path / "uploads"
    graph_path = tmp_path / "graphs"
    upload_path.mkdir(parents=True, exist_ok=True)
    graph_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("UPLOAD_DIR", str(upload_path))
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_path))
    monkeypatch.setenv("SCHOLARGRAPH_IGNORE_DOTENV", "1")
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    reset_persistence_singletons()
    await init_isolated_database(db_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, upload_path, graph_path
    reset_persistence_singletons()
    get_settings.cache_clear()


def _make_pdf(upload_dir: Path, name: str) -> Path:
    pdf_path = upload_dir / name
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "API delete PDF.")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


async def _seed_ready(paper_id: str, pdf_path: Path) -> None:
    await PaperRepository().create(paper_id, "api delete", str(pdf_path), status=PaperStatus.READY)
    await PipelineRepository().save_status(
        paper_id,
        PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.READY,
            percent=STAGE_PERCENT[PipelineStage.READY],
            stage=PipelineStage.READY,
            message="ready",
            updated_at=datetime.now(UTC),
        ),
    )


async def _seed_processing(paper_id: str, pdf_path: Path) -> None:
    await PaperRepository().create(
        paper_id,
        "api delete processing",
        str(pdf_path),
        status=PaperStatus.PROCESSING,
    )
    await PipelineRepository().save_status(
        paper_id,
        PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.PROCESSING,
            percent=STAGE_PERCENT[PipelineStage.EXTRACTING],
            stage=PipelineStage.EXTRACTING,
            message="extracting",
            updated_at=datetime.now(UTC),
        ),
    )


@pytest.mark.asyncio
async def test_api_delete_ready_returns_204(api_env) -> None:
    client, upload_path, _graph = api_env
    paper_id = "api-delete-ready"
    pdf = _make_pdf(upload_path, f"{paper_id}.pdf")
    await _seed_ready(paper_id, pdf)

    vector_store = AsyncMock()
    vector_store.delete_by_paper = AsyncMock()
    with patch(
        "backend.services.paper_delete_service._resolve_vector_store",
        return_value=vector_store,
    ):
        response = await client.delete(f"/api/v1/papers/{paper_id}")

    assert response.status_code == 204
    assert await PaperRepository().get(paper_id) is None
    assert not pdf.is_file()


@pytest.mark.asyncio
async def test_api_delete_processing_without_force_409(api_env) -> None:
    client, upload_path, _graph = api_env
    paper_id = "api-delete-proc-409"
    pdf = _make_pdf(upload_path, f"{paper_id}.pdf")
    await _seed_processing(paper_id, pdf)

    response = await client.delete(f"/api/v1/papers/{paper_id}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PAPER_ALREADY_PROCESSING"


@pytest.mark.asyncio
async def test_api_delete_processing_with_force_204(api_env) -> None:
    client, upload_path, _graph = api_env
    paper_id = "api-delete-proc-force"
    pdf = _make_pdf(upload_path, f"{paper_id}.pdf")
    await _seed_processing(paper_id, pdf)

    vector_store = AsyncMock()
    vector_store.delete_by_paper = AsyncMock()
    with patch(
        "backend.services.paper_delete_service._resolve_vector_store",
        return_value=vector_store,
    ):
        response = await client.delete(f"/api/v1/papers/{paper_id}?force=true")

    assert response.status_code == 204
    assert await PaperRepository().get(paper_id) is None


@pytest.mark.asyncio
async def test_force_reextract_overrides_409(api_env) -> None:
    client, upload_path, _graph = api_env
    paper_id = "api-reextract-force"
    pdf = _make_pdf(upload_path, f"{paper_id}.pdf")
    await _seed_processing(paper_id, pdf)
    get_paper_service.cache_clear()

    blocked = await client.post(f"/api/v1/papers/{paper_id}/reextract")
    assert blocked.status_code == 409

    with patch("backend.services.reextract_service.schedule_paper_pipeline") as scheduler:
        forced = await client.post(f"/api/v1/papers/{paper_id}/reextract?force=true")

    assert forced.status_code == 200
    assert forced.json()["data"]["status"] == "pending"
    scheduler.assert_called_once()
