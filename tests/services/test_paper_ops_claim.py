"""Unit tests for durable paper_ops_claims cluster wipe mutex."""

from __future__ import annotations

import pytest
from backend.db.models import PAPER_OPS_OPERATION_DELETE, PAPER_OPS_OPERATION_REEXTRACT
from backend.repositories.paper_ops_claim_repository import (
    PaperOpsClaimConflictError,
    get_paper_ops_claim_repository,
)
from backend.services.paper_ops_claim import (
    acquire_paper_ops_claim,
    force_release_paper_ops_claim_sync,
    is_paper_ops_claim_held,
    release_paper_ops_claim,
)
from backend.services.pipeline_task_registry import abort_in_flight_pipeline


@pytest.mark.asyncio
async def test_try_acquire_conflicts_while_live(persistence_env) -> None:
    repo = get_paper_ops_claim_repository()
    paper_id = "ops-claim-unit"
    token = await repo.try_acquire(paper_id, operation=PAPER_OPS_OPERATION_REEXTRACT)
    with pytest.raises(PaperOpsClaimConflictError):
        await repo.try_acquire(paper_id, operation=PAPER_OPS_OPERATION_DELETE)
    assert await repo.release(paper_id, token)
    assert not await repo.is_held(paper_id)


@pytest.mark.asyncio
async def test_abort_does_not_drop_owned_wipe_claim(persistence_env) -> None:
    """force_reextract / delete must keep the claim across abort_in_flight_pipeline."""
    paper_id = "ops-claim-survives-abort"
    owner = await acquire_paper_ops_claim(paper_id, operation=PAPER_OPS_OPERATION_REEXTRACT)
    assert is_paper_ops_claim_held(paper_id)
    await abort_in_flight_pipeline(paper_id)
    assert is_paper_ops_claim_held(paper_id)
    await release_paper_ops_claim(paper_id, owner)
    assert not is_paper_ops_claim_held(paper_id)


@pytest.mark.asyncio
async def test_force_release_sync_evicts_abandoned_claim(persistence_env) -> None:
    paper_id = "ops-claim-force-evict"
    await get_paper_ops_claim_repository().seed_claim_for_tests(
        paper_id,
        operation=PAPER_OPS_OPERATION_DELETE,
    )
    assert is_paper_ops_claim_held(paper_id)
    force_release_paper_ops_claim_sync(paper_id)
    assert not is_paper_ops_claim_held(paper_id)
