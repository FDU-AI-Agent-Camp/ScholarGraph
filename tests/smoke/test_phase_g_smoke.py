"""Phase G smoke: classifier modules, settings, status field sanity."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from backend.agents.classifier_constants import (
    CLASSIFIER_HEURISTIC_FALLBACK_CODE,
    CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
)
from backend.agents.classifier_llm import CLASSIFIER_PROMPT_PATH, load_classifier_prompt
from backend.agents.classifier_types import ClassifyResult
from backend.config import Settings
from backend.main import app
from backend.schemas.paper import PaperStatusData
from httpx import ASGITransport, AsyncClient

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"


@pytest.mark.smoke
def test_smoke_classifier_prompt_file_exists() -> None:
    assert CLASSIFIER_PROMPT_PATH.is_file()


@pytest.mark.smoke
def test_smoke_load_classifier_prompt_returns_non_empty() -> None:
    assert len(load_classifier_prompt().strip()) > 20


@pytest.mark.smoke
def test_smoke_classifier_settings_registered() -> None:
    settings = Settings(_env_file=None)
    assert hasattr(settings, "classifier_llm_enabled")
    assert hasattr(settings, "classifier_heuristic_fallback")


@pytest.mark.smoke
def test_smoke_classifier_warning_constants_frozen() -> None:
    assert CLASSIFIER_HEURISTIC_FALLBACK_CODE == "classifier_heuristic_fallback"
    assert CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE == "触发分类启发式Fallback!"


@pytest.mark.smoke
def test_smoke_classify_result_importable() -> None:
    assert ClassifyResult.__name__ == "ClassifyResult"


@pytest.mark.smoke
def test_smoke_paper_status_data_accepts_classify_warnings() -> None:
    status = PaperStatusData.model_validate(
        {
            "paper_id": "smoke-g",
            "status": "ready",
            "percent": 100,
            "stage": "ready",
            "message": "建图完成",
            "updated_at": "2026-06-07T00:00:00Z",
            "classify_warnings": [CLASSIFIER_HEURISTIC_FALLBACK_CODE],
        },
    )
    assert status.classify_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]


@pytest.mark.smoke
def test_smoke_classifier_live_path_wires_llm_and_fallback() -> None:
    from backend.agents import classifier

    source = inspect.getsource(classifier.classify)
    assert "is_llm_mock" in source
    assert "_classify_live" in source


@pytest.mark.smoke
def test_smoke_openapi_yaml_mentions_classify_warnings() -> None:
    openapi = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.yaml"
    text = openapi.read_text(encoding="utf-8")
    assert "classify_warnings:" in text


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_get_paper_status_route_includes_classify_warnings() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/papers/hss-001/status")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "classify_warnings" in data
        assert isinstance(data["classify_warnings"], list)


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_smoke_get_paper_detail_route_includes_classify_warnings() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/papers/hss-001")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "classify_warnings" in data
        assert isinstance(data["classify_warnings"], list)


@pytest.mark.smoke
def test_smoke_papers_list_fixture_still_validates() -> None:
    payload = json.loads((FIXTURES_DIR / "papers-list.json").read_text(encoding="utf-8"))
    assert payload["data"]["items"]
