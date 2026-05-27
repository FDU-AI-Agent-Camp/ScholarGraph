"""Pipeline status/stage/percent updates aligned with api-contract §2."""

from functools import lru_cache

from backend.graph.state import STAGE_PERCENT
from backend.schemas.paper import PaperStatus, PaperStatusData, PipelineStage
from backend.services.paper_service import get_paper_service

PROCESSING_STAGES: frozenset[PipelineStage] = frozenset(
    {
        PipelineStage.INGESTING,
        PipelineStage.CLASSIFYING,
        PipelineStage.EXTRACTING,
        PipelineStage.STORING,
    },
)

DEFAULT_STAGE_MESSAGES: dict[PipelineStage, str] = {
    PipelineStage.INGESTING: "正在解析 PDF",
    PipelineStage.CLASSIFYING: "正在识别范式与理论视角…",
    PipelineStage.EXTRACTING: "正在抽取逻辑图谱",
    PipelineStage.STORING: "正在写入图谱存储",
    PipelineStage.READY: "建图完成",
    PipelineStage.FAILED: "流水线失败",
}


def validate_status_contract(
    *,
    status: PaperStatus,
    stage: PipelineStage | None,
    percent: int,
) -> None:
    """Enforce api-contract rules for status vs stage vs percent."""
    if status == PaperStatus.PENDING:
        if stage is not None:
            msg = "status=pending 时 stage 必须为 null"
            raise ValueError(msg)
        if percent != 0:
            msg = "status=pending 时 percent 必须为 0"
            raise ValueError(msg)
        return

    if status == PaperStatus.PROCESSING:
        if stage not in PROCESSING_STAGES:
            msg = f"status=processing 时 stage 必须为 {sorted(s.value for s in PROCESSING_STAGES)} 之一"
            raise ValueError(msg)
        expected_percent = STAGE_PERCENT[stage]
        if percent != expected_percent:
            msg = f"stage={stage.value} 时 percent 必须为 {expected_percent}"
            raise ValueError(msg)
        return

    if status == PaperStatus.READY:
        if stage != PipelineStage.READY or percent != 100:
            raise ValueError("status=ready 时 stage=ready 且 percent=100")
        return

    if status == PaperStatus.FAILED:
        if stage != PipelineStage.FAILED or percent != 0:
            raise ValueError("status=failed 时 stage=failed 且 percent=0")
        return

    raise ValueError(f"未知 status: {status}")


def validate_failed_error_fields(
    *,
    status: PaperStatus,
    error_code: str | None,
    failed_during: PipelineStage | None,
) -> None:
    """failed 态必须带 error_code；failed_during 仅允许处理中阶段。"""
    if status == PaperStatus.FAILED:
        if not error_code or not error_code.strip():
            raise ValueError("status=failed 时 error_code 必填")
        if failed_during is not None and failed_during not in PROCESSING_STAGES:
            msg = f"failed_during 必须为 {sorted(s.value for s in PROCESSING_STAGES)} 之一"
            raise ValueError(msg)
        return

    if error_code is not None or failed_during is not None:
        raise ValueError("非 failed 状态不得包含 error_code / failed_during")


class PipelineStatusService:
    """Single entry for workflow progress writes consumed by GET .../status."""

    def start_processing(self, paper_id: str, *, message: str | None = None) -> PaperStatusData:
        """pending → processing，进入 ingesting（percent=20）。"""
        return self.advance_stage(
            paper_id,
            PipelineStage.INGESTING,
            message=message or "流水线已启动，正在解析 PDF",
        )

    def advance_stage(
        self,
        paper_id: str,
        stage: PipelineStage,
        *,
        message: str | None = None,
    ) -> PaperStatusData:
        if stage not in PROCESSING_STAGES:
            raise ValueError(f"advance_stage 不接受终态 stage: {stage}")
        percent = STAGE_PERCENT[stage]
        msg = message or DEFAULT_STAGE_MESSAGES[stage]
        return self._apply(
            paper_id,
            status=PaperStatus.PROCESSING,
            stage=stage,
            percent=percent,
            message=msg,
        )

    def mark_ready(self, paper_id: str, *, message: str | None = None) -> PaperStatusData:
        return self._apply(
            paper_id,
            status=PaperStatus.READY,
            stage=PipelineStage.READY,
            percent=STAGE_PERCENT[PipelineStage.READY],
            message=message or DEFAULT_STAGE_MESSAGES[PipelineStage.READY],
        )

    def mark_failed(
        self,
        paper_id: str,
        *,
        message: str,
        error_code: str,
        failed_during: PipelineStage | None = None,
    ) -> PaperStatusData:
        return self._apply(
            paper_id,
            status=PaperStatus.FAILED,
            stage=PipelineStage.FAILED,
            percent=STAGE_PERCENT[PipelineStage.FAILED],
            message=message,
            error_code=error_code,
            failed_during=failed_during,
        )

    def _apply(
        self,
        paper_id: str,
        *,
        status: PaperStatus,
        stage: PipelineStage | None,
        percent: int,
        message: str,
        error_code: str | None = None,
        failed_during: PipelineStage | None = None,
    ) -> PaperStatusData:
        validate_status_contract(status=status, stage=stage, percent=percent)
        validate_failed_error_fields(
            status=status,
            error_code=error_code,
            failed_during=failed_during,
        )
        return get_paper_service().set_status_snapshot(
            paper_id,
            status=status,
            stage=stage,
            percent=percent,
            message=message,
            error_code=error_code,
            failed_during=failed_during,
        )


@lru_cache
def get_pipeline_status_service() -> PipelineStatusService:
    return PipelineStatusService()
