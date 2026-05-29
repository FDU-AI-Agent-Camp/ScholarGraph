"""PatrolService error mapping tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from backend.api.exceptions import ApiError
from backend.schemas.patrol import PatrolInsight, PatrolMode, PatrolReport
from backend.services.patrol_service import PatrolService


async def test_patrol_service_maps_patrol_error_to_api_error() -> None:
    service = PatrolService()
    with patch("backend.services.patrol_service.patrol_run", new_callable=AsyncMock) as run:
        from backend.patrol.errors import PatrolError

        run.side_effect = PatrolError("GRAPH_NOT_READY", "图谱未就绪: hss-002", status_code=409)
        with pytest.raises(ApiError) as exc_info:
            await service.run_patrol(["hss-001", "hss-002"], PatrolMode.LENS_CLASH)
    assert exc_info.value.code == "GRAPH_NOT_READY"
    assert exc_info.value.status_code == 409


async def test_patrol_service_returns_delegated_report() -> None:
    service = PatrolService()
    expected = PatrolReport(
        mode=PatrolMode.LENS_CLASH,
        paper_ids=["hss-001", "hss-002"],
        insights=[
            PatrolInsight(
                insight_id="ins-001",
                title="理论视角冲突（Lens Clash）",
                summary="mock",
                paper_ids=["hss-001", "hss-002"],
                node_refs=[],
            ),
        ],
        generated_at=datetime(2026, 5, 19, 11, 0, tzinfo=UTC),
    )
    with patch("backend.services.patrol_service.patrol_run", new_callable=AsyncMock) as run:
        run.return_value = expected
        result = await service.run_patrol(["hss-001", "hss-002"], PatrolMode.LENS_CLASH)
    assert result == expected
    run.assert_awaited_once_with(["hss-001", "hss-002"], PatrolMode.LENS_CLASH)
