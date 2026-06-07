"""Phase F smoke: extract modules, settings, status field sanity."""

from __future__ import annotations

import inspect

import pytest
from backend.agents.extract_constants import (
    EXTRACT_HEURISTIC_FALLBACK_CODE,
    EXTRACT_HEURISTIC_FALLBACK_MESSAGE,
)
from backend.agents.extract_llm import PROMPTS_DIR, load_extract_prompt
from backend.agents.extract_types import ExtractResult
from backend.config import Settings
from backend.main import app
from backend.schemas.paper import PaperStatusData
from httpx import ASGITransport, AsyncClient


@pytest.mark.smoke
def test_smoke_extract_prompt_files_exist() -> None:
    assert (PROMPTS_DIR / "extract_hss.md").is_file()
    assert (PROMPTS_DIR / "extract_stem.md").is_file()


@pytest.mark.smoke
def test_smoke_load_extract_prompt_returns_non_empty() -> None:
    from backend.schemas.paradigm import Paradigm

    assert len(load_extract_prompt(Paradigm.HSS).strip()) > 20
    assert len(load_extract_prompt(Paradigm.STEM).strip()) > 20


@pytest.mark.smoke
def test_smoke_extract_llm_logs_truncation() -> None:
    from backend.agents import extract_llm

    source = inspect.getsource(extract_llm.extract_with_llm)
    assert "extract_input_truncated" in source


@pytest.mark.smoke
def test_smoke_extract_settings_registered() -> None:
    settings = Settings(_env_file=None)
    assert hasattr(settings, "extract_llm_enabled")
    assert hasattr(settings, "extract_max_input_chars")
    assert hasattr(settings, "extract_heuristic_fallback")


@pytest.mark.smoke
def test_smoke_extract_warning_constants_frozen() -> None:
    assert EXTRACT_HEURISTIC_FALLBACK_CODE == "extract_heuristic_fallback"
    assert EXTRACT_HEURISTIC_FALLBACK_MESSAGE == "触发启发式Fallback!"


@pytest.mark.smoke
def test_smoke_extract_result_importable() -> None:
    assert ExtractResult.__name__ == "ExtractResult"


@pytest.mark.smoke
def test_smoke_paper_status_data_accepts_extract_warnings() -> None:
    status = PaperStatusData.model_validate(
        {
            "paper_id": "smoke-f",
            "status": "ready",
            "percent": 100,
            "stage": "ready",
            "message": "建图完成",
            "updated_at": "2026-06-07T00:00:00Z",
            "extract_warnings": [EXTRACT_HEURISTIC_FALLBACK_CODE],
        },
    )
    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.smoke
def test_smoke_f22_fallback_helper_wired() -> None:
    from backend.agents import extractor

    source = inspect.getsource(extractor._fallback_to_heuristic)
    assert "extract_llm_fallback" in source
    assert "build_heuristic_graph" in source


@pytest.mark.smoke
def test_smoke_f22_heuristic_legacy_aliases_importable() -> None:
    from backend.agents import extract_heuristic

    assert callable(extract_heuristic._build_hss_graph)
    assert callable(extract_heuristic._build_stem_graph)


@pytest.mark.smoke
def test_smoke_f22_validate_llm_graph_checks_edges() -> None:
    from backend.agents.extract_llm import _validate_llm_graph

    assert "no edges" in inspect.getsource(_validate_llm_graph)


@pytest.mark.smoke
def test_smoke_f23_paper_detail_schema_has_extract_warnings() -> None:
    from datetime import UTC, datetime

    from backend.schemas.paper import PaperDetail, PaperStatus

    now = datetime.now(UTC)
    detail = PaperDetail(
        paper_id="smoke-f23",
        title="smoke",
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
        extract_warnings=[EXTRACT_HEURISTIC_FALLBACK_CODE],
    )
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in detail.extract_warnings


@pytest.mark.smoke
def test_smoke_f23_fixtures_on_disk() -> None:
    from pathlib import Path

    fixtures = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"
    assert (fixtures / "paper-detail-ready-fallback.json").is_file()
    assert (fixtures / "paper-status-ready-fallback.json").is_file()


@pytest.mark.smoke
def test_smoke_f23_paper_service_enrich_detail() -> None:
    from backend.services.paper_service import PaperService

    assert "_enrich_paper_detail" in inspect.getsource(PaperService.get_paper)


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_get_paper_route_includes_extract_warnings() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/papers/hss-001")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "extract_warnings" in data
        assert isinstance(data["extract_warnings"], list)


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_status_route_includes_extract_warnings() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/papers/hss-001/status")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "extract_warnings" in data
        assert isinstance(data["extract_warnings"], list)
