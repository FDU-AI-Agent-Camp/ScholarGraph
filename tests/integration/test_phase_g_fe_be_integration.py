"""G5 FE↔BE 联调：classify_warnings 机器码与前端冻结文案成对验收。

与 ``frontend/src/test/phase-g-fe-be.integration.test.ts`` 成对。
与 ``tests/integration/test_phase_g_fe_be_integration.py`` 引用互链。
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.agents.classifier_constants import (
    CLASSIFIER_HEURISTIC_FALLBACK_CODE,
    CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE,
)
from backend.main import app
from backend.schemas.paper import PaperDetail, PaperStatus, PaperStatusData
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_status_service import get_pipeline_status_service
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"
FE_CLASSIFY_WARNINGS = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "utils" / "classifyWarnings.ts"
)
CLASSIFY_FALLBACK_PAPER_ID = "hss-classify-fallback-001"
FROZEN_MESSAGE = "触发分类启发式Fallback!"


def _read_frontend_frozen_message() -> str:
    text = FE_CLASSIFY_WARNINGS.read_text(encoding="utf-8")
    match = re.search(r"CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE = '([^']+)'", text)
    assert match is not None
    return match.group(1)


@pytest.fixture
async def api_client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _register_classify_fallback_paper() -> None:
    detail_payload = json.loads((FIXTURES_DIR / "paper-detail-classify-fallback.json").read_text(encoding="utf-8"))
    status_payload = json.loads((FIXTURES_DIR / "paper-status-classify-fallback.json").read_text(encoding="utf-8"))
    detail_data = detail_payload["data"]
    status_data = status_payload["data"]

    now = datetime.now(UTC)
    get_paper_service()._papers[CLASSIFY_FALLBACK_PAPER_ID] = PaperDetail(
        paper_id=CLASSIFY_FALLBACK_PAPER_ID,
        title=detail_data["title"],
        status=PaperStatus.READY,
        created_at=now,
        updated_at=now,
        paradigm=Paradigm.STEM,
        classification=ParadigmClassification.model_validate(detail_data["classification"]),
    )
    get_pipeline_status_service().mark_ready(CLASSIFY_FALLBACK_PAPER_ID)
    get_paper_service().record_classify_warnings(
        CLASSIFY_FALLBACK_PAPER_ID,
        status_data["classify_warnings"],
    )


def test_g5_fe_be_frozen_message_parity() -> None:
    assert CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE == FROZEN_MESSAGE
    assert _read_frontend_frozen_message() == CLASSIFIER_HEURISTIC_FALLBACK_MESSAGE


def test_g5_openapi_fixtures_use_machine_code_not_user_copy() -> None:
    for name in ("paper-detail-classify-fallback.json", "paper-status-classify-fallback.json"):
        payload = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
        warnings = payload["data"]["classify_warnings"]
        assert warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
        assert FROZEN_MESSAGE not in json.dumps(payload["data"], ensure_ascii=False)


@pytest.mark.asyncio
async def test_g5_be_api_status_matches_fixture_for_fe_polling(api_client: AsyncClient) -> None:
    expected = json.loads((FIXTURES_DIR / "paper-status-classify-fallback.json").read_text(encoding="utf-8"))[
        "data"
    ]
    _register_classify_fallback_paper()

    response = await api_client.get(f"/api/v1/papers/{CLASSIFY_FALLBACK_PAPER_ID}/status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert PaperStatusData.model_validate(data)
    assert data["classify_warnings"] == expected["classify_warnings"]
    assert FROZEN_MESSAGE not in data["classify_warnings"]


@pytest.mark.asyncio
async def test_g5_be_api_detail_matches_fixture_for_fe_detail_alert(api_client: AsyncClient) -> None:
    expected = json.loads((FIXTURES_DIR / "paper-detail-classify-fallback.json").read_text(encoding="utf-8"))[
        "data"
    ]
    _register_classify_fallback_paper()

    response = await api_client.get(f"/api/v1/papers/{CLASSIFY_FALLBACK_PAPER_ID}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["classify_warnings"] == expected["classify_warnings"]
    assert set(data["classification"].keys()) == {"paradigm", "confidence", "reason"}
    assert "classify_warnings" not in data["classification"]
    assert FROZEN_MESSAGE not in json.dumps(data, ensure_ascii=False)


@pytest.mark.asyncio
async def test_g5_be_status_and_detail_classify_warnings_consistent_for_fe(api_client: AsyncClient) -> None:
    _register_classify_fallback_paper()

    status_resp = await api_client.get(f"/api/v1/papers/{CLASSIFY_FALLBACK_PAPER_ID}/status")
    detail_resp = await api_client.get(f"/api/v1/papers/{CLASSIFY_FALLBACK_PAPER_ID}")

    status_warnings = status_resp.json()["data"]["classify_warnings"]
    detail_warnings = detail_resp.json()["data"]["classify_warnings"]
    assert status_warnings == detail_warnings == [CLASSIFIER_HEURISTIC_FALLBACK_CODE]
