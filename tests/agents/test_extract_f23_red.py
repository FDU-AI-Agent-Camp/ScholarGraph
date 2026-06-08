"""
F.2.3 红灯测试（extract_warnings 边界）

运行：uv run pytest -m red tests/agents/test_extract_f23_red.py -rx
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.schemas.paper import PaperDetail, PaperStatus, PaperStatusData
from backend.services.paper_service import get_paper_service

pytestmark = pytest.mark.red


@pytest.fixture
def registered_paper() -> str:
    paper_id = "f23-red-paper"
    now = datetime.now(UTC)
    service = get_paper_service()
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="f23 red test",
        status=PaperStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    service._status.pop(paper_id, None)
    service._head_refine_warnings.pop(paper_id, None)
    service._extract_warnings.pop(paper_id, None)
    return paper_id


@pytest.mark.asyncio
async def test_red_record_extract_warnings_empty_list_is_noop(registered_paper: str) -> None:
    service = get_paper_service()
    service.record_extract_warnings(registered_paper, [EXTRACT_HEURISTIC_FALLBACK_CODE])
    service.record_extract_warnings(registered_paper, [])

    status = await service.get_status(registered_paper)
    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]


@pytest.mark.asyncio
async def test_red_unknown_extract_warning_code_stored_and_returned(registered_paper: str) -> None:
    service = get_paper_service()
    service.record_extract_warnings(registered_paper, ["unknown_future_code"])

    status = await service.get_status(registered_paper)
    paper = await service.get_paper(registered_paper)

    assert status.extract_warnings == ["unknown_future_code"]
    assert paper.extract_warnings == ["unknown_future_code"]


@pytest.mark.asyncio
async def test_red_get_paper_without_recorded_warnings_returns_empty_list(registered_paper: str) -> None:
    service = get_paper_service()
    service._extract_warnings.pop(registered_paper, None)

    paper = await service.get_paper(registered_paper)

    assert paper.extract_warnings == []


def test_red_paper_detail_model_omitting_extract_warnings_defaults_empty() -> None:
    now = datetime.now(UTC)
    detail = PaperDetail.model_validate(
        {
            "paper_id": "red-detail-default",
            "title": "t",
            "status": "ready",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    )
    assert detail.extract_warnings == []


def test_red_paper_status_data_rejects_non_list_extract_warnings() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PaperStatusData(
            paper_id="red-invalid",
            status=PaperStatus.READY,
            percent=100,
            message="ok",
            updated_at=datetime.now(UTC),
            extract_warnings="not-a-list",  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_red_head_refine_and_extract_warnings_are_independent(registered_paper: str) -> None:
    service = get_paper_service()
    service.record_head_refine_warnings(registered_paper, ["mineru_unavailable"])
    service.record_extract_warnings(registered_paper, [EXTRACT_HEURISTIC_FALLBACK_CODE])

    status = await service.get_status(registered_paper)

    assert "mineru_unavailable" in status.head_refine_warnings
    assert status.extract_warnings == [EXTRACT_HEURISTIC_FALLBACK_CODE]
