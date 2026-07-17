# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Property-style chaos lifecycle tests for D6 ephemeral pipeline state."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto

import pytest
from backend.schemas.graph import GraphEdge, GraphNode, UnifiedPaperGraph
from backend.schemas.paper import PaperStatus
from backend.schemas.paradigm import Paradigm
from backend.services.paper_service import PaperService, get_paper_service
from tests.helpers.persistence_testkit import (
    register_test_paper,
    restart_paper_service,
    simulate_service_crash,
)

CHAOS_SEED = 20260713
CHAOS_ACTION_COUNT = 60


class _Action(Enum):
    CREATE_PAPER = auto()
    SET_PROCESSING = auto()
    SAVE_PREVIEW = auto()
    SET_ACTIVE_RUN_ID = auto()
    RECORD_WARNING = auto()
    CRASH_RESTART = auto()
    CLEAR_PREVIEW = auto()
    CLEAR_EPHEMERAL = auto()
    VERIFY = auto()


@dataclass
class _PaperEphemeralState:
    active_run_id: str | None = None
    preview_graph: UnifiedPaperGraph | None = None


@dataclass
class _ChaosModel:
    papers: dict[str, _PaperEphemeralState] = field(default_factory=dict)
    next_paper_index: int = 0
    next_run_index: int = 0


def _preview_for(paper_id: str, *, token: str) -> UnifiedPaperGraph:
    return UnifiedPaperGraph(
        paper_id=paper_id,
        paradigm=Paradigm.HSS,
        nodes=[
            GraphNode(
                id=f"n-{token}",
                label=f"preview-{token}",
                type="Thesis",
                data={"chaos": {"token": token}},
            ),
        ],
        edges=[
            GraphEdge(
                id=f"e-{token}",
                source=f"n-{token}",
                target=f"n-{token}",
                label="REF",
                type="REF",
            ),
        ],
    )


def _assert_matches_model(service: PaperService, model: _ChaosModel) -> None:
    for paper_id, expected in model.papers.items():
        actual_run_id = service.get_active_run_id(paper_id)
        assert actual_run_id == expected.active_run_id, (
            f"active_run_id mismatch for {paper_id}: {actual_run_id!r} != {expected.active_run_id!r}"
        )
        actual_preview = service.get_preview_graph(paper_id)
        if expected.preview_graph is None:
            assert actual_preview is None, f"preview_graph should be cleared for {paper_id}"
        else:
            assert actual_preview is not None, f"preview_graph missing for {paper_id}"
            assert actual_preview.model_dump(mode="json") == expected.preview_graph.model_dump(mode="json")


async def _apply_action(
    action: _Action,
    *,
    service: PaperService,
    model: _ChaosModel,
    rng: random.Random,
) -> PaperService:
    if action == _Action.CREATE_PAPER:
        paper_id = f"chaos-{model.next_paper_index:03d}"
        model.next_paper_index += 1
        await register_test_paper(paper_id, status=PaperStatus.PENDING)
        model.papers[paper_id] = _PaperEphemeralState()
        return service

    if not model.papers:
        return await _apply_action(_Action.CREATE_PAPER, service=service, model=model, rng=rng)

    paper_id = rng.choice(list(model.papers.keys()))
    state = model.papers[paper_id]

    if action == _Action.SET_PROCESSING:
        from backend.repositories.pipeline_repository import PipelineRepository
        from backend.schemas.paper import PaperStatusData, PipelineStage

        await PipelineRepository().save_status(
            paper_id,
            PaperStatusData(
                paper_id=paper_id,
                status=PaperStatus.PROCESSING,
                percent=rng.randint(1, 95),
                stage=PipelineStage.EXTRACTING,
                message="chaos-processing",
                updated_at=datetime.now(UTC),
            ),
        )
        return service

    if action == _Action.SAVE_PREVIEW:
        token = f"{model.next_run_index}-{rng.randint(0, 999)}"
        model.next_run_index += 1
        preview = _preview_for(paper_id, token=token)
        service.save_preview_graph(paper_id, preview)
        service.mark_preview_available(paper_id)
        state.preview_graph = preview
        return service

    if action == _Action.SET_ACTIVE_RUN_ID:
        run_id = f"chaos-run-{model.next_run_index}"
        model.next_run_index += 1
        service.set_active_run_id(paper_id, run_id)
        state.active_run_id = run_id
        return service

    if action == _Action.RECORD_WARNING:
        service.record_extract_warnings(paper_id, [f"chaos_warning_{rng.randint(0, 99)}"])
        return service

    if action == _Action.CRASH_RESTART:
        simulate_service_crash()
        restarted = await restart_paper_service()
        _assert_matches_model(restarted, model)
        return restarted

    if action == _Action.CLEAR_PREVIEW:
        from backend.repositories.pipeline_repository import PipelineRepository

        await PipelineRepository().clear_preview_graph(paper_id)
        state.preview_graph = None
        return service

    if action == _Action.CLEAR_EPHEMERAL:
        service.clear_ephemeral_pipeline_state(paper_id)
        state.preview_graph = None
        state.active_run_id = None
        return service

    if action == _Action.VERIFY:
        _assert_matches_model(service, model)
        return service

    msg = f"Unhandled chaos action: {action}"
    raise AssertionError(msg)


@pytest.mark.asyncio
async def test_ephemeral_state_chaos_lifecycle_invariants(persistence_env) -> None:
    """Randomized action sequences keep DB-backed ephemeral state aligned with the model."""
    rng = random.Random(CHAOS_SEED)
    model = _ChaosModel()
    service = get_paper_service()

    weighted_actions = [
        _Action.CREATE_PAPER,
        _Action.SET_PROCESSING,
        _Action.SAVE_PREVIEW,
        _Action.SAVE_PREVIEW,
        _Action.SET_ACTIVE_RUN_ID,
        _Action.SET_ACTIVE_RUN_ID,
        _Action.RECORD_WARNING,
        _Action.CRASH_RESTART,
        _Action.CLEAR_PREVIEW,
        _Action.CLEAR_EPHEMERAL,
        _Action.VERIFY,
    ]

    for _step in range(CHAOS_ACTION_COUNT):
        action = rng.choice(weighted_actions)
        service = await _apply_action(action, service=service, model=model, rng=rng)
        _assert_matches_model(service, model)

    simulate_service_crash()
    final_service = await restart_paper_service()
    _assert_matches_model(final_service, model)
