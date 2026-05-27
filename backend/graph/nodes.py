"""LangGraph node handlers — orchestration only; all domain work in services."""

from pathlib import Path

from backend.graph.state import STAGE_PERCENT, WorkflowState
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm
from backend.services.agent_service import get_agent_service
from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError
from backend.services.ingest_service import get_ingest_service
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_completion_service import get_pipeline_completion_service


def _mark_progress(
    state: WorkflowState,
    *,
    stage: PipelineStage,
    message: str,
) -> None:
    get_paper_service().update_pipeline_status(
        state["paper_id"],
        status=PaperStatus.PROCESSING,
        stage=stage,
        percent=STAGE_PERCENT[stage],
        message=message,
    )


def _failure_patch(exc: ServiceError, *, stage: PipelineStage) -> WorkflowState:
    return WorkflowState(
        failed=True,
        error_code=exc.code,
        error_message=exc.message,
        stage=stage,
        message=exc.message,
    )


def _success_patch(
    *,
    stage: PipelineStage,
    message: str,
    **fields: object,
) -> WorkflowState:
    patch: WorkflowState = {
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


async def classify_node(state: WorkflowState) -> WorkflowState:
    _mark_progress(state, stage=PipelineStage.CLASSIFYING, message="正在范式分类")
    try:
        classification = await get_agent_service().classify_paradigm(state["classifier_input"])
    except ServiceError as exc:
        return _failure_patch(exc, stage=PipelineStage.CLASSIFYING)

    return _success_patch(
        stage=PipelineStage.CLASSIFYING,
        message="范式分类完成",
        classification=classification.model_dump(mode="json"),
        paradigm=classification.paradigm.value,
    )


async def extract_node(state: WorkflowState) -> WorkflowState:
    _mark_progress(state, stage=PipelineStage.EXTRACTING, message="正在抽取逻辑图谱")
    try:
        graph = await get_agent_service().extract_graph(
            state["full_text"],
            Paradigm(state["paradigm"]),
            paper_id=state["paper_id"],
        )
    except ServiceError as exc:
        return _failure_patch(exc, stage=PipelineStage.EXTRACTING)

    return _success_patch(
        stage=PipelineStage.EXTRACTING,
        message="图谱抽取完成",
        graph=graph.model_dump(mode="json"),
    )


async def store_node(state: WorkflowState) -> WorkflowState:
    _mark_progress(state, stage=PipelineStage.STORING, message="正在写入图谱存储")
    try:
        get_pipeline_completion_service().finalize(
            state["paper_id"],
            graph_data=state["graph"],
            classification_data=state["classification"],
        )
    except ServiceError as exc:
        return _failure_patch(exc, stage=PipelineStage.STORING)

    return WorkflowState(
        status=PaperStatus.READY,
        stage=PipelineStage.READY,
        percent=STAGE_PERCENT[PipelineStage.READY],
        message="建图完成",
        failed=False,
    )


async def fail_node(state: WorkflowState) -> WorkflowState:
    paper_id = state["paper_id"]
    message = state.get("error_message") or state.get("message") or "流水线失败"
    code = state.get("error_code", PIPELINE_FAILED_CODE)
    get_paper_service().fail_pipeline(paper_id, message=message, error_code=code)
    return WorkflowState(
        status=PaperStatus.FAILED,
        stage=PipelineStage.FAILED,
        percent=0,
        message=message,
        failed=True,
    )
