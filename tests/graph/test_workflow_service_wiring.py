"""Verify workflow nodes connect to business layer only through service facades."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from backend.agents.classifier_types import ClassifyResult
from backend.agents.extract_types import ExtractResult
from backend.graph import nodes
from backend.graph.state import WorkflowState, initial_workflow_state
from backend.schemas.graph import GraphNode, UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.graph_persistence_service import GraphPersistenceService
from backend.services.pipeline_completion_service import PipelineCompletionService


async def test_wait_head_refine_node_reaches_be_via_head_refine_wait(
    post_ingest_state: WorkflowState,
) -> None:
    with (
        patch("backend.graph.nodes.ensure_head_refine_scheduled") as schedule,
        patch(
            "backend.graph.nodes.wait_for_refined_classifier_input",
            new_callable=AsyncMock,
            return_value=("REFINED", ["mineru_unavailable"]),
        ) as wait_fn,
    ):
        out = await nodes.wait_head_refine_node(post_ingest_state)

    schedule.assert_called_once()
    wait_fn.assert_awaited_once()
    assert out["classifier_input"] == "REFINED"
    assert out["head_refine_warnings"] == ["mineru_unavailable"]


async def test_ingest_node_reaches_be_only_via_ingest_service(
    workflow_paper: tuple[str, Path],
) -> None:
    paper_id, pdf_path = workflow_paper
    state = initial_workflow_state(paper_id=paper_id, pdf_path=str(pdf_path))
    payload = {
        "paper_id": paper_id,
        "full_text": "FULL",
        "classifier_input": "SNIP",
    }
    with patch("backend.services.ingest_service.ingest_pdf", new_callable=AsyncMock) as raw:
        raw.return_value = payload
        out = await nodes.ingest_node(state)

    raw.assert_awaited_once_with(pdf_path, paper_id=paper_id)
    assert out["full_text"] == "FULL"
    assert out.get("failed") is not True


async def test_classify_node_reaches_be_only_via_agent_service(
    post_ingest_state: WorkflowState,
) -> None:
    classification = ParadigmClassification(
        paradigm=Paradigm.HSS,
        confidence=0.9,
        reason="r",
    )
    with patch("backend.services.agent_service.classify", new_callable=AsyncMock) as raw:
        raw.return_value = ClassifyResult(classification=classification, warnings=[])
        out = await nodes.classify_node(post_ingest_state)

    raw.assert_awaited_once_with(post_ingest_state["classifier_input"])
    assert out["paradigm"] == "HSS"


async def test_extract_node_reaches_be_only_via_agent_service(
    post_classify_state: WorkflowState,
) -> None:
    graph = UnifiedPaperGraph(
        paper_id=post_classify_state["paper_id"],
        paradigm=Paradigm.HSS,
        nodes=[GraphNode(id="n1", label="n", type="Thesis")],
        edges=[],
    )
    with patch("backend.graph.nodes.get_agent_service") as get_svc:
        agent = MagicMock()
        agent.extract_graph = AsyncMock(return_value=ExtractResult(graph=graph, warnings=[]))
        agent.should_extract_in_background = MagicMock(return_value=False)
        get_svc.return_value = agent
        out = await nodes.extract_node(post_classify_state)

    agent.extract_graph.assert_awaited_once_with(
        post_classify_state["full_text"],
        Paradigm.HSS,
        paper_id=post_classify_state["paper_id"],
    )
    assert out["graph"]["paper_id"] == post_classify_state["paper_id"]


async def test_store_node_reaches_persistence_via_completion_service(
    post_extract_state: WorkflowState,
) -> None:
    saved: list[UnifiedPaperGraph] = []
    store = MagicMock()
    store.save = lambda g: saved.append(g)
    persistence = GraphPersistenceService(store=store)
    completion = PipelineCompletionService(graph_persistence=persistence)

    with patch("backend.graph.nodes.get_pipeline_completion_service", return_value=completion):
        out = await nodes.store_node(post_extract_state)

    assert len(saved) == 1
    assert saved[0].paper_id == post_extract_state["paper_id"]
    # P10: store step returns INDEXING; READY follows EventBus RAG promote.
    assert out["status"] == "indexing"


async def test_nodes_never_call_be_when_services_are_mocked_at_boundary(
    workflow_paper: tuple[str, Path],
) -> None:
    """Mock only service getters on nodes; BE modules must stay uncalled."""
    paper_id, pdf_path = workflow_paper
    state = initial_workflow_state(paper_id=paper_id, pdf_path=str(pdf_path))

    ingest_svc = MagicMock()
    ingest_svc.ingest = AsyncMock(
        return_value={
            "paper_id": paper_id,
            "full_text": "t",
            "classifier_input": "c",
        },
    )
    with (
        patch("backend.graph.nodes.get_ingest_service", return_value=ingest_svc),
        patch("backend.services.ingest_service.ingest_pdf", new_callable=AsyncMock) as raw_ingest,
    ):
        await nodes.ingest_node(state)
        ingest_svc.ingest.assert_awaited_once()
        raw_ingest.assert_not_awaited()
