"""LangGraph node handlers — orchestration only; all domain work in services."""

import logging
from pathlib import Path

from backend.graph.state import STAGE_PERCENT, WorkflowState
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.agent_service import get_agent_service
from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError
from backend.services.head_refine_wait import wait_for_refined_classifier_input
from backend.services.ingest_service import get_ingest_service
from backend.services.paper_pipeline_scheduler import ensure_head_refine_scheduled
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_completion_service import get_pipeline_completion_service
from backend.services.pipeline_status_service import get_pipeline_status_service

RAG_INDEX_STAGE_MESSAGE = "正在构建 RAG 向量索引"

logger = logging.getLogger(__name__)


def _mark_progress(
    state: WorkflowState,
    *,
    stage: PipelineStage,
    message: str,
) -> PaperStatusData:
    return get_pipeline_status_service().advance_stage(
        state["paper_id"],
        stage,
        message=message,
    )


def _failure_patch(exc: ServiceError, *, stage: PipelineStage) -> WorkflowState:
    return WorkflowState(
        failed=True,
        error_code=exc.code,
        error_message=exc.message,
        status=PaperStatus.PROCESSING,
        stage=stage,
        percent=STAGE_PERCENT[stage],
        message=exc.message,
    )


def _success_patch(
    *,
    stage: PipelineStage,
    message: str,
    **fields: object,
) -> WorkflowState:
    patch: WorkflowState = {
        "status": PaperStatus.PROCESSING,
        "stage": stage,
        "percent": STAGE_PERCENT[stage],
        "message": message,
        "failed": False,
    }
    for key, value in fields.items():
        patch[key] = value  # type: ignore[literal-required]
    return patch


async def ingest_node(state: WorkflowState) -> WorkflowState:
    _mark_progress(state, stage=PipelineStage.INGESTING, message="正在解析 PDF")
    try:
        result = await get_ingest_service().ingest(
            Path(state["pdf_path"]),
            paper_id=state["paper_id"],
        )
    except ServiceError as exc:
        return _failure_patch(exc, stage=PipelineStage.INGESTING)

    return _success_patch(
        stage=PipelineStage.INGESTING,
        message="PDF 解析完成",
        full_text=result["full_text"],
        classifier_input=result["classifier_input"],
    )


async def wait_head_refine_node(state: WorkflowState) -> WorkflowState:
    """Wait for async path-B + rules merge, then replace ``classifier_input`` (P4)."""
    _mark_progress(state, stage=PipelineStage.HEAD_REFINING, message="正在精炼文档头部…")
    paper_id = state["paper_id"]
    pdf_path = Path(state["pdf_path"])
    fallback = state.get("classifier_input", "")

    ensure_head_refine_scheduled(paper_id, pdf_path)
    refined, warnings = await wait_for_refined_classifier_input(
        paper_id,
        pdf_path,
        fallback,
    )
    if warnings:
        get_paper_service().record_head_refine_warnings(paper_id, warnings)

    _mark_progress(state, stage=PipelineStage.HEAD_REFINING, message="文档头部精炼完成")

    return _success_patch(
        stage=PipelineStage.HEAD_REFINING,
        message="文档头部精炼完成",
        classifier_input=refined,
        head_refine_warnings=warnings,
    )


async def classify_node(state: WorkflowState) -> WorkflowState:
    _mark_progress(state, stage=PipelineStage.CLASSIFYING, message="正在范式分类")
    paper_id = state["paper_id"]
    try:
        result = await get_agent_service().classify_paradigm(state["classifier_input"])
    except ServiceError as exc:
        return _failure_patch(exc, stage=PipelineStage.CLASSIFYING)

    if result.warnings:
        get_paper_service().record_classify_warnings(paper_id, result.warnings)

    classification = result.classification
    return _success_patch(
        stage=PipelineStage.CLASSIFYING,
        message="范式分类完成",
        classification=classification.model_dump(mode="json"),
        paradigm=classification.paradigm.value,
        classify_warnings=result.warnings,
    )


async def extract_node(state: WorkflowState) -> WorkflowState:
    _mark_progress(state, stage=PipelineStage.EXTRACTING, message="正在抽取逻辑图谱")
    paper_id = state["paper_id"]
    paradigm = Paradigm(state["paradigm"])
    agent_service = get_agent_service()

    if agent_service.should_extract_in_background(state["full_text"]):
        try:
            classification = ParadigmClassification.model_validate(state["classification"])
            result = await agent_service.extract_graph_background(
                state["full_text"],
                paradigm,
                paper_id=paper_id,
                classification=classification,
            )
        except ServiceError as exc:
            return _failure_patch(exc, stage=PipelineStage.EXTRACTING)

        if result.warnings:
            get_paper_service().record_extract_warnings(paper_id, result.warnings)

        return _success_patch(
            stage=PipelineStage.EXTRACTING,
            message="全量抽取已在后台启动，可先预览 MVP 骨架",
            graph=result.graph.model_dump(mode="json"),
            extract_warnings=result.warnings,
            background_extraction_scheduled=True,
        )

    try:
        result = await agent_service.extract_graph(
            state["full_text"],
            paradigm,
            paper_id=paper_id,
        )
    except ServiceError as exc:
        return _failure_patch(exc, stage=PipelineStage.EXTRACTING)

    if result.warnings:
        get_paper_service().record_extract_warnings(paper_id, result.warnings)

    return _success_patch(
        stage=PipelineStage.EXTRACTING,
        message="图谱抽取完成",
        graph=result.graph.model_dump(mode="json"),
        extract_warnings=result.warnings,
    )


async def store_node(state: WorkflowState) -> WorkflowState:
    _mark_progress(state, stage=PipelineStage.STORING, message="正在写入图谱存储")
    try:
        graph = get_pipeline_completion_service().finalize(
            state["paper_id"],
            graph_data=state["graph"],
            classification_data=state["classification"],
            extract_warnings=state.get("extract_warnings"),
        )
    except ServiceError as exc:
        return _failure_patch(exc, stage=PipelineStage.STORING)

    # Build the RAG vector index asynchronously without blocking the ready status.
    # Failures are captured as extract_warnings so the paper can still be usable.
    try:
        await _index_paper_for_rag_async(state["paper_id"], full_text=state["full_text"], graph=graph)
    except Exception:
        # RAG indexing is best-effort; failures are already recorded as warnings
        # by index_paper_for_rag. The paper must still reach ready.
        logger.exception("rag_index_failed_in_store_node", extra={"paper_id": state["paper_id"]})

    return WorkflowState(
        status=PaperStatus.READY,
        stage=PipelineStage.READY,
        percent=STAGE_PERCENT[PipelineStage.READY],
        message="建图完成",
        failed=False,
    )


async def _index_paper_for_rag_async(
    paper_id: str,
    *,
    full_text: str,
    graph: UnifiedPaperGraph,
) -> None:
    """Build RAG vector index in the background; surface failures as warnings."""

    from backend.config import get_settings
    from backend.rag.handlers import index_paper_for_rag
    from backend.rag.vector_store import VectorStore
    from backend.services.paper_service import get_paper_service

    _mark_progress(
        WorkflowState(paper_id=paper_id),
        stage=PipelineStage.STORING,
        message=RAG_INDEX_STAGE_MESSAGE,
    )
    settings = get_settings()
    vector_store = VectorStore(
        chroma_path=settings.chromadb_path,
        paper_service=get_paper_service(),
    )
    await index_paper_for_rag(
        paper_id,
        full_text=full_text,
        graph=graph,
        vector_store=vector_store,
        suppress_errors=True,
    )


async def fail_node(state: WorkflowState) -> WorkflowState:
    paper_id = state["paper_id"]
    message = state.get("error_message") or state.get("message") or "流水线失败"
    failed_during = state.get("stage")
    failed_stage: PipelineStage | None = failed_during if isinstance(failed_during, PipelineStage) else None
    error_code = state.get("error_code", PIPELINE_FAILED_CODE)
    get_pipeline_status_service().mark_failed(
        paper_id,
        message=message,
        error_code=error_code,
        failed_during=failed_stage,
    )
    return WorkflowState(
        status=PaperStatus.FAILED,
        stage=PipelineStage.FAILED,
        percent=STAGE_PERCENT[PipelineStage.FAILED],
        message=message,
        error_code=error_code,
        failed_during=failed_stage,
        failed=True,
    )
