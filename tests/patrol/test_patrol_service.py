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
    run.assert_awaited_once_with(
        ["hss-001", "hss-002"],
        PatrolMode.LENS_CLASH,
        store=None,
        vector_store=service._vector_store,
    )


async def test_patrol_service_injects_default_vector_store(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from backend.services import patrol_service as ps_module

    mock = AsyncMock()
    monkeypatch.setattr(ps_module, "get_patrol_service", lambda: ps_module.PatrolService(vector_store=mock))
    service = ps_module.get_patrol_service()
    assert service._vector_store is not None


async def test_patrol_service_maps_method_overlap_insufficient_data_to_api_error() -> None:
    service = PatrolService()
    with patch("backend.services.patrol_service.patrol_run", new_callable=AsyncMock) as run:
        from backend.patrol.errors import PatrolError

        run.side_effect = PatrolError(
            "PATROL_INSUFFICIENT_DATA",
            "未找到可比较的 Method 节点",
            status_code=422,
        )
        with pytest.raises(ApiError) as exc_info:
            await service.run_patrol(["stem-001", "stem-002"], PatrolMode.METHOD_OVERLAP)
    assert exc_info.value.code == "PATROL_INSUFFICIENT_DATA"
    assert exc_info.value.status_code == 422


async def test_patrol_service_delegates_method_overlap_with_vector_store() -> None:
    service = PatrolService()
    expected = PatrolReport(
        mode=PatrolMode.METHOD_OVERLAP,
        paper_ids=["stem-001", "stem-002"],
        insights=[],
        generated_at=datetime(2026, 5, 19, 11, 0, tzinfo=UTC),
    )
    with patch("backend.services.patrol_service.patrol_run", new_callable=AsyncMock) as run:
        run.return_value = expected
        result = await service.run_patrol(["stem-001", "stem-002"], PatrolMode.METHOD_OVERLAP)
    assert result == expected
    run.assert_awaited_once_with(
        ["stem-001", "stem-002"],
        PatrolMode.METHOD_OVERLAP,
        store=None,
        vector_store=service._vector_store,
    )


async def test_patrol_service_maps_claim_evolution_insufficient_data_to_api_error() -> None:
    service = PatrolService()
    with patch("backend.services.patrol_service.patrol_run", new_callable=AsyncMock) as run:
        from backend.patrol.errors import PatrolError

        run.side_effect = PatrolError(
            "PATROL_INSUFFICIENT_DATA",
            "无法构建观点演进巡检洞察",
            status_code=422,
        )
        with pytest.raises(ApiError) as exc_info:
            await service.run_patrol(["stem-001", "stem-002"], PatrolMode.CLAIM_EVOLUTION)
    assert exc_info.value.code == "PATROL_INSUFFICIENT_DATA"
    assert exc_info.value.status_code == 422


async def test_patrol_service_delegates_claim_evolution_with_vector_store() -> None:
    service = PatrolService()
    expected = PatrolReport(
        mode=PatrolMode.CLAIM_EVOLUTION,
        paper_ids=["stem-001", "stem-002"],
        insights=[],
        generated_at=datetime(2026, 5, 19, 11, 0, tzinfo=UTC),
    )
    with patch("backend.services.patrol_service.patrol_run", new_callable=AsyncMock) as run:
        run.return_value = expected
        result = await service.run_patrol(["stem-001", "stem-002"], PatrolMode.CLAIM_EVOLUTION)
    assert result == expected
    run.assert_awaited_once_with(
        ["stem-001", "stem-002"],
        PatrolMode.CLAIM_EVOLUTION,
        store=None,
        vector_store=service._vector_store,
    )
