"""Phase E deliverables checklist (progress.md §5 Phase E.2).

Maps P7–P11 to automated static / schema regression checks.
"""

from __future__ import annotations

from pathlib import Path

from backend.graph.head_store import HeadStore
from backend.graph.state import STAGE_PERCENT
from backend.schemas.ingest_head import IngestHead, PersistedHeadRefine
from backend.schemas.paper import FailedDuringStage, PaperDetail, PaperStatusData, PipelineStage
from backend.services.pipeline_status_service import PROCESSING_STAGES

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI = REPO_ROOT / "docs" / "api" / "openapi.yaml"
GRAPH_DIR = REPO_ROOT / "backend" / "graph"


def test_phase_e_p7_head_refining_stage_in_processing_set() -> None:
    assert PipelineStage.HEAD_REFINING in PROCESSING_STAGES
    assert STAGE_PERCENT[PipelineStage.HEAD_REFINING] == 35


def test_phase_e_p7_failed_during_includes_head_refining() -> None:
    assert FailedDuringStage.HEAD_REFINING.value == "head_refining"


def test_phase_e_p8_paper_status_data_exposes_head_refine_warnings() -> None:
    status = PaperStatusData.model_validate(
        {
            "paper_id": "p8",
            "status": "processing",
            "percent": 35,
            "stage": "head_refining",
            "message": "正在精炼文档头部…",
            "updated_at": "2026-06-07T00:00:00Z",
            "head_refine_warnings": ["mineru_unavailable"],
        },
    )
    assert status.head_refine_warnings == ["mineru_unavailable"]


def test_phase_e_p9_health_route_exposes_grobid_probe() -> None:
    import inspect

    from backend.api.routes import health

    source = inspect.getsource(health.health)
    assert "grobid_connected" in source
    assert "grobid_note" in source


def test_phase_e_p8_openapi_status_documents_head_refine_warnings() -> None:
    text = OPENAPI.read_text(encoding="utf-8")
    assert "head_refine_warnings:" in text
    assert "PaperStatusData:" in text


def test_phase_e_p10_head_store_module_exists() -> None:
    assert (GRAPH_DIR / "head_store.py").is_file()
    assert callable(HeadStore().save)
    assert callable(HeadStore().load)


def test_phase_e_p10_persisted_head_refine_schema_round_trip() -> None:
    record = PersistedHeadRefine(
        paper_id="audit-1",
        merged=IngestHead(title="T", sources={"title": "mineru"}),
        classifier_input="Title: T",
        warnings=["mineru_unavailable"],
    )
    restored = PersistedHeadRefine.model_validate_json(record.model_dump_json())
    assert restored.merged.sources["title"] == "mineru"


def test_phase_e_p11_paper_detail_supports_ingest_head_sources() -> None:
    detail = PaperDetail.model_validate(
        {
            "paper_id": "p11",
            "title": "demo",
            "status": "ready",
            "created_at": "2026-06-07T00:00:00Z",
            "ingest_head": {
                "title": "Merged",
                "abstract": "",
                "keywords": "",
                "intro": "",
                "sources": {"title": "grobid", "abstract": "pymupdf"},
            },
        },
    )
    assert detail.ingest_head is not None
    assert detail.ingest_head.sources["title"] == "grobid"


def test_phase_e_p11_openapi_documents_ingest_head_on_paper_detail() -> None:
    text = OPENAPI.read_text(encoding="utf-8")
    assert "IngestHead:" in text
    assert "ingest_head:" in text
    assert "sources:" in text
