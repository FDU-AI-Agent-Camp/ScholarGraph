"""Exception propagation: ServiceError → node failed state → fail_node → PaperService."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.graph import nodes
from backend.graph.state import WorkflowState
from backend.graph.workflow import run_paper_pipeline
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.services.errors import ServiceError
from backend.services.paper_service import get_paper_service


@pytest.mark.parametrize(
    ("node_fn", "state_fixture", "service_getter", "service_method", "error", "expected_code", "expected_stage"),
    [
        (
            nodes.ingest_node,
            "workflow_initial_state",
            "get_ingest_service",
            "ingest",
            ServiceError("INGEST_FAILED", "bad pdf"),
            "INGEST_FAILED",
            PipelineStage.INGESTING,
        ),
        (
            nodes.classify_node,
            "post_ingest_state",
            "get_agent_service",
            "classify_paradigm",
            ServiceError("LLM_JSON_INVALID", "bad json"),
            "LLM_JSON_INVALID",
            PipelineStage.CLASSIFYING,
        ),
        (
            nodes.extract_node,
            "post_classify_state",
            "get_agent_service",
            "extract_graph",
            ServiceError("PIPELINE_FAILED", "no extractor"),
            "PIPELINE_FAILED",
            PipelineStage.EXTRACTING,
        ),
        (
            nodes.store_node,
            "post_extract_state",
            "get_pipeline_completion_service",
            "finalize",
            ServiceError("PIPELINE_FAILED", "save failed"),
            "PIPELINE_FAILED",
            PipelineStage.STORING,
        ),
    ],
)
async def test_node_maps_service_error_to_failed_workflow_state(
    node_fn,
    state_fixture: str,
    service_getter: str,
    service_method: str,
    error: ServiceError,
    expected_code: str,
    expected_stage: PipelineStage,
    request: pytest.FixtureRequest,
) -> None:
    state: WorkflowState = request.getfixturevalue(state_fixture)
    svc = MagicMock()
    if service_method == "finalize":
        mock_method = MagicMock(side_effect=error)
    else:
        mock_method = AsyncMock(side_effect=error)
    setattr(svc, service_method, mock_method)
    patch_target = f"backend.graph.nodes.{service_getter}"
    with patch(patch_target, return_value=svc):
        out = await node_fn(state)

    assert out.get("failed") is True
    assert out.get("error_code") == expected_code
    assert out.get("stage") == expected_stage
    assert out.get("error_message") == error.message
    assert out.get("message") == error.message


async def test_fail_node_persists_error_to_paper_service(
    workflow_paper: tuple[str, Path],
) -> None:
    paper_id, _ = workflow_paper
    state = WorkflowState(
        paper_id=paper_id,
        error_code="INGEST_FAILED",
        error_message="无法解析",
        failed=True,
    )
    await nodes.fail_node(state)
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED
    assert status.stage == PipelineStage.FAILED
    assert status.message == "无法解析"
    assert status.error_code == "INGEST_FAILED"


@pytest.mark.parametrize(
    ("service_getter", "service_method", "error"),
    [
        ("get_ingest_service", "ingest", ServiceError("INGEST_FAILED", "ingest err")),
        ("get_agent_service", "classify_paradigm", ServiceError("LLM_JSON_INVALID", "cls err")),
        ("get_agent_service", "extract_graph", ServiceError("PIPELINE_FAILED", "ext err")),
    ],
)
async def test_pipeline_end_to_end_failure_updates_paper_status(
    workflow_paper: tuple[str, Path],
    service_getter: str,
    service_method: str,
    error: ServiceError,
) -> None:
    paper_id, pdf_path = workflow_paper
    svc = MagicMock()
    if service_method == "ingest":
        svc.ingest = AsyncMock(side_effect=error)
    elif service_method == "classify_paradigm":
        svc.classify_paradigm = AsyncMock(side_effect=error)
    else:
        svc.extract_graph = AsyncMock(side_effect=error)

    patch_target = f"backend.graph.nodes.{service_getter}"
    with patch(patch_target, return_value=svc):
        final = await run_paper_pipeline(paper_id, pdf_path)

    assert final.get("failed") is True
    status = await get_paper_service().get_status(paper_id)
    assert status.status == PaperStatus.FAILED
