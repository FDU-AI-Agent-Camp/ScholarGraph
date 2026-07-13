"""Compat shim behavior tests (D8 test-only helpers)."""

from __future__ import annotations

import pytest
from backend.schemas.paper import PaperStatus
from backend.services.paper_service import get_paper_service
from tests.helpers.compat_shims import COMPAT_PAPER_ID_PAGE_SIZE, CompatPaperDict, CompatStatusDict
from tests.helpers.persistence_testkit import register_test_paper

COMPAT_ITER_PAGE_SIZE = COMPAT_PAPER_ID_PAGE_SIZE


@pytest.mark.asyncio
async def test_compat_paper_dict_iter_uses_pagination_not_single_burst(persistence_env, monkeypatch) -> None:
    service = get_paper_service()
    for index in range(3):
        await register_test_paper(f"page-{index}", title=f"p{index}", status=PaperStatus.PENDING)

    compat = CompatPaperDict(service)
    list_calls: list[tuple[int, int]] = []

    original_list = service._paper_repo.list

    async def _recording_list(*, offset: int = 0, limit: int = 20, **kwargs):
        list_calls.append((offset, limit))
        return await original_list(offset=offset, limit=limit, **kwargs)

    monkeypatch.setattr(service._paper_repo, "list", _recording_list)

    ids = list(compat)
    assert len(ids) == 3
    page_calls = [call for call in list_calls if call[1] == COMPAT_PAPER_ID_PAGE_SIZE]
    assert page_calls
    assert max(offset for offset, _ in page_calls) == 0


@pytest.mark.asyncio
async def test_compat_status_dict_delitem_deletes_pipeline_row(persistence_env) -> None:
    paper_id = "compat-del-status"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    service = get_paper_service()
    compat = CompatStatusDict(service)

    assert compat[paper_id].status == PaperStatus.PROCESSING
    del compat[paper_id]
    with pytest.raises(KeyError):
        _ = compat[paper_id]


@pytest.mark.asyncio
async def test_legacy_del_service_status_teardown_purges_pipeline_row(persistence_env) -> None:
    """Legacy ``del service._status[paper_id]`` must complete CRUD teardown without NotImplementedError."""
    from backend.repositories.pipeline_repository import PipelineRepository

    paper_id = "legacy-teardown-status"
    await register_test_paper(paper_id, status=PaperStatus.PROCESSING)
    service = get_paper_service()

    assert service._status[paper_id].status == PaperStatus.PROCESSING
    assert await service._pipeline_repo.get_latest(paper_id) is not None

    del service._status[paper_id]

    assert await service._pipeline_repo.get_latest(paper_id) is None
    fresh_repo = PipelineRepository()
    assert await fresh_repo.get_latest(paper_id) is None
    with pytest.raises(KeyError):
        _ = service._status[paper_id]
