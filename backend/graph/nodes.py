"""LangGraph node handlers — delegate to BE module Services only."""

from pathlib import Path

from backend.agents.classifier import classify
from backend.agents.extractor import extract
from backend.graph.state import STAGE_PERCENT, WorkflowState
from backend.ingest.pdf import ingest_pdf
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paper import PaperStatus, PipelineStage
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.graph.store import GraphStore
from backend.services.paper_service import get_paper_service

PIPELINE_FAILED_CODE = "PIPELINE_FAILED"


def _mark_progress(
    state: WorkflowState,
    *,
    stage: PipelineStage,
    message: str,
) -> None:
    paper_id = state["paper_id"]
    percent = STAGE_PERCENT[stage]
    get_paper_service().update_pipeline_status(
        paper_id,
        status=PaperStatus.PROCESSING,
        stage=stage,
        percent=percent,
        message=message,
    )


async def ingest_node(state: WorkflowState) -> WorkflowState:
    paper_id = state["paper_id"]
    pdf_path = Path(state["pdf_path"])
    _mark_progress(state, stage=PipelineStage.INGESTING, message="正在解析 PDF")

    try:
        result = await ingest_pdf(pdf_path, paper_id=paper_id)
    except NotImplementedError as exc:
        return _failure_patch(stage=PipelineStage.INGESTING, message=str(exc))
    except Exception as exc:
        return _failure_patch(
            stage=PipelineStage.INGESTING,
            message=f"PDF 解析失败: {exc}",
            code="INGEST_FAILED",
        )

    return WorkflowState(
        full_text=result["full_text"],
        classifier_input=result["classifier_input"],
        stage=PipelineStage.INGESTING,
        percent=STAGE_PERCENT[PipelineStage.INGESTING],
        message="PDF 解析完成",
        failed=False,
    )


async def classify_node(state: WorkflowState) -> WorkflowState:
    _mark_progress(state, stage=PipelineStage.CLASSIFYING, message="正在范式分类")

    try:
        classification = await classify(state["classifier_input"])
    except NotImplementedError as exc:
        return _failure_patch(stage=PipelineStage.CLASSIFYING, message=str(exc))
    except Exception as exc:
        return _failure_patch(
            stage=PipelineStage.CLASSIFYING,
            message=f"范式分类失败: {exc}",
            code="LLM_JSON_INVALID",
        )

    return WorkflowState(
        classification=classification.model_dump(mode="json"),
        paradigm=classification.paradigm.value,
        stage=PipelineStage.CLASSIFYING,
        percent=STAGE_PERCENT[PipelineStage.CLASSIFYING],
        message="范式分类完成",
        failed=False,
    )


async def extract_node(state: WorkflowState) -> WorkflowState:
    paradigm = Paradigm(state["paradigm"])
    _mark_progress(state, stage=PipelineStage.EXTRACTING, message="正在抽取逻辑图谱")

    try:
        graph = await extract(state["full_text"], paradigm)
    except NotImplementedError as exc:
        return _failure_patch(stage=PipelineStage.EXTRACTING, message=str(exc))
    except Exception as exc:
        return _failure_patch(
            stage=PipelineStage.EXTRACTING,
            message=f"图谱抽取失败: {exc}",
            code="LLM_JSON_INVALID",
        )

    graph = graph.model_copy(update={"paper_id": state["paper_id"], "paradigm": paradigm})
    return WorkflowState(
        graph=graph.model_dump(mode="json"),
        stage=PipelineStage.EXTRACTING,
        percent=STAGE_PERCENT[PipelineStage.EXTRACTING],
        message="图谱抽取完成",
        failed=False,
    )


async def store_node(state: WorkflowState) -> WorkflowState:
    paper_id = state["paper_id"]
    _mark_progress(state, stage=PipelineStage.STORING, message="正在写入图谱存储")

    try:
        graph = UnifiedPaperGraph.model_validate(state["graph"])
        GraphStore().save(graph)
        classification = ParadigmClassification.model_validate(state["classification"])
        get_paper_service().complete_pipeline(
            paper_id,
            classification=classification,
            graph=graph,
        )
    except Exception as exc:
        return _failure_patch(
            stage=PipelineStage.STORING,
            message=f"图谱存储失败: {exc}",
            code=PIPELINE_FAILED_CODE,
        )

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


def _failure_patch(
    *,
    stage: PipelineStage,
    message: str,
    code: str = PIPELINE_FAILED_CODE,
) -> WorkflowState:
    return WorkflowState(
        failed=True,
        error_code=code,
        error_message=message,
        stage=stage,
        message=message,
    )
