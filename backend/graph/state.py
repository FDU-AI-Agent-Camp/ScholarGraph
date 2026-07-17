# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""LangGraph workflow state for the single-paper pipeline."""

from typing import Any, TypedDict

from backend.schemas.paper import PaperStatus, PipelineStage

# Node names (stable identifiers for the StateGraph).
NODE_INGEST = "ingest"
NODE_WAIT_HEAD_REFINE = "wait_head_refine"
NODE_CLASSIFY = "classify"
NODE_EXTRACT = "extract"
NODE_STORE = "store"
NODE_FAIL = "fail"

PIPELINE_ORDER: tuple[str, ...] = (
    NODE_INGEST,
    NODE_WAIT_HEAD_REFINE,
    NODE_CLASSIFY,
    NODE_EXTRACT,
    NODE_STORE,
)

# Suggested polling percents (api-contract / tech-stack).
STAGE_PERCENT: dict[PipelineStage, int] = {
    PipelineStage.INGESTING: 20,
    PipelineStage.HEAD_REFINING: 35,
    PipelineStage.CLASSIFYING: 50,
    PipelineStage.EXTRACTING: 80,
    PipelineStage.STORING: 95,
    PipelineStage.INDEXING: 98,
    PipelineStage.READY: 100,
    PipelineStage.FAILED: 0,
}


class WorkflowState(TypedDict, total=False):
    """State passed between LangGraph nodes; keys are merged incrementally."""

    paper_id: str
    pdf_path: str

    status: PaperStatus
    stage: PipelineStage | None
    percent: int
    message: str

    error_code: str
    error_message: str
    failed_during: PipelineStage | None

    full_text: str
    classifier_input: str
    page_break_offsets: list[int]

    classification: dict[str, Any]
    paradigm: str

    graph: dict[str, Any]

    head_refine_warnings: list[str]
    classify_warnings: list[str]
    extract_warnings: list[str]

    # Slice 2: long papers schedule full extraction in the background.
    background_extraction_scheduled: bool

    # Extract-generation token for terminal write guard (see pipeline_generation_guard).
    pipeline_generation_id: str

    failed: bool


def initial_workflow_state(
    *,
    paper_id: str,
    pdf_path: str,
    pipeline_generation_id: str | None = None,
) -> WorkflowState:
    state = WorkflowState(
        paper_id=paper_id,
        pdf_path=pdf_path,
        status=PaperStatus.PROCESSING,
        stage=PipelineStage.INGESTING,
        percent=STAGE_PERCENT[PipelineStage.INGESTING],
        message="流水线已启动，正在解析 PDF",
        failed=False,
    )
    if pipeline_generation_id is not None:
        state["pipeline_generation_id"] = pipeline_generation_id
    return state
