# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Phase C pipeline integration checklist (progress.md §5 Phase C).

Maps C1–C10 deliverables to automated regression checks.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.config import Settings
from backend.graph.state import NODE_WAIT_HEAD_REFINE, PIPELINE_ORDER
from backend.graph.workflow import build_paper_pipeline_graph
from backend.ingest.router import IngestRouteKind, resolve_ingest_route
from backend.services.head_refine_wait import HEAD_REFINE_TIMEOUT_WARNING

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICES_DIR = REPO_ROOT / "backend" / "services"
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def test_phase_c_c1_config_exposes_ingest_and_grobid_settings() -> None:
    settings = Settings(_env_file=None)
    assert settings.ingest_route in ("auto", "pymupdf_only")
    assert settings.ingest_short_page_limit == 25
    assert settings.grobid_url.startswith("http")
    assert settings.ingest_mineru_timeout_seconds >= 60
    assert settings.grobid_timeout_seconds >= 60


def test_phase_c_c2_env_example_documents_ingest_section() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "INGEST_ROUTE" in text
    assert "GROBID_URL" in text
    assert "INGEST_HEAD_LLM_ENABLED" in text


def test_phase_c_c3_router_auto_dispatch() -> None:
    settings = Settings(_env_file=None, ingest_route="auto", ingest_short_page_limit=25)
    assert resolve_ingest_route(25, settings=settings) == IngestRouteKind.SHORT
    assert resolve_ingest_route(26, settings=settings) == IngestRouteKind.LONG


def test_phase_c_c5_wait_module_exists() -> None:
    assert (SERVICES_DIR / "head_refine_wait.py").is_file()


def test_phase_c_c5_workflow_includes_wait_head_refine_node() -> None:
    assert NODE_WAIT_HEAD_REFINE in PIPELINE_ORDER
    assert PIPELINE_ORDER.index(NODE_WAIT_HEAD_REFINE) == 1
    graph = build_paper_pipeline_graph()
    assert NODE_WAIT_HEAD_REFINE in graph.nodes


def test_phase_c_c6_production_rules_merge_env_default_documented() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "INGEST_HEAD_LLM_ENABLED" in text


def test_phase_c_c7_c8_degrade_warning_constant() -> None:
    """Timeout and path-B failures surface machine-readable warnings."""
    assert HEAD_REFINE_TIMEOUT_WARNING == "head_refine_timeout"


@pytest.mark.parametrize(
    ("module_name",),
    [
        ("head_refine_service.py",),
        ("head_merge_service.py",),
        ("paper_pipeline_scheduler.py",),
    ],
)
def test_phase_c_async_pipeline_modules_exist(module_name: str) -> None:
    path = SERVICES_DIR / module_name
    assert path.is_file(), f"missing Phase C module: {path}"


def test_phase_c_c9_health_route_imports_grobid_probe() -> None:
    import inspect

    from backend.api.routes import health

    source = inspect.getsource(health.health)
    assert "check_grobid_isalive" in source
    assert "grobid_connected" in source
