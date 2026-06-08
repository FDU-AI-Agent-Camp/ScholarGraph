"""Phase A/B ingest deliverables checklist (progress.md §5 Phase A–B).

Maps progress tasks B1–B5 and Phase A GROBID spike artifacts to automated checks.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from backend.ingest.grobid_client import PROCESS_FULLTEXT_PATH, fetch_grobid_tei
from backend.ingest.head_merge import merge_with_rules
from backend.ingest.mineru_backend import is_mineru_available, run_mineru_pipeline
from backend.ingest.router import IngestRouteKind, resolve_ingest_route
from backend.ingest.tei_parser import parse_tei_to_head_candidate

REPO_ROOT = Path(__file__).resolve().parents[2]
INGEST_DIR = REPO_ROOT / "backend" / "ingest"
BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "benchmark_dual_route.py"
GROBID_COMPOSE = REPO_ROOT / "docker-compose.grobid.yml"
TEI_FIXTURE = Path(__file__).parent / "fixtures" / "grobid_sample.tei.xml"
BENCHMARK_REPORT_DIR = REPO_ROOT / "data" / "benchmark_reports"

PHASE_A_INGEST_MODULES = ("grobid_client.py", "tei_parser.py")
PHASE_B_INGEST_MODULES = (
    "router.py",
    "mineru_backend.py",
    "head_merge.py",
    "head_candidates.py",
)


# ── Phase A: GROBID environment + TEI spike ──────────────────────────────────


def test_phase_a_docker_compose_grobid_sidecar() -> None:
    """Phase A: CRF sidecar on 8070 with memory limit."""
    assert GROBID_COMPOSE.is_file()
    text = GROBID_COMPOSE.read_text(encoding="utf-8")
    assert "grobid/grobid:0.9.0-crf" in text
    assert "8070:8070" in text
    assert "mem_limit" in text


@pytest.mark.parametrize("module_name", PHASE_A_INGEST_MODULES)
def test_phase_a_ingest_modules_exist(module_name: str) -> None:
    path = INGEST_DIR / module_name
    assert path.is_file(), f"missing Phase A module: {path}"


def test_phase_a_b1_tei_parser_fixture_extracts_grobid_fields() -> None:
    """B1: tei_parser + fixture TEI → HeadCandidate."""
    tei = TEI_FIXTURE.read_text(encoding="utf-8")
    candidate = parse_tei_to_head_candidate(tei)
    assert candidate.source == "grobid"
    assert candidate.title == "Sample GROBID Title"
    assert candidate.abstract.strip()
    assert candidate.keywords.strip()
    assert candidate.intro.strip()


@pytest.mark.asyncio
async def test_phase_a_b2_grobid_client_posts_fulltext_endpoint(tmp_path: Path) -> None:
    """B2: grobid_client calls processFulltextDocument and returns TEI."""
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% grobid client test")

    mock_response = MagicMock()
    mock_response.text = TEI_FIXTURE.read_text(encoding="utf-8")
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.ingest.grobid_client.httpx.AsyncClient", return_value=mock_client):
        tei = await fetch_grobid_tei(pdf_path)

    assert tei is not None
    assert "<TEI" in tei
    mock_client.post.assert_awaited_once()
    call_kwargs = mock_client.post.await_args
    assert call_kwargs is not None
    url = call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs.get("url", "")
    assert PROCESS_FULLTEXT_PATH in url


@pytest.mark.asyncio
async def test_phase_a_b2_grobid_client_returns_none_on_http_error(tmp_path: Path) -> None:
    pdf_path = tmp_path / "bad.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.ingest.grobid_client.httpx.AsyncClient", return_value=mock_client):
        tei = await fetch_grobid_tei(pdf_path)

    assert tei is None


@pytest.mark.asyncio
@pytest.mark.live_grobid
async def test_phase_a_grobid_isalive_when_sidecar_running() -> None:
    """Optional live check: docker compose -f docker-compose.grobid.yml up -d."""
    from backend.config import get_settings

    url = get_settings().grobid_url.rstrip("/") + "/api/isalive"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
    except httpx.HTTPError:
        pytest.skip(f"GROBID 不可达: {url}")

    if response.status_code != 200:
        pytest.skip(f"GROBID isalive 非 200: {response.status_code}")
    assert "true" in response.text.lower()


# ── Phase B: parser modules + benchmark ──────────────────────────────────────


@pytest.mark.parametrize("module_name", PHASE_B_INGEST_MODULES)
def test_phase_b_ingest_modules_exist(module_name: str) -> None:
    path = INGEST_DIR / module_name
    assert path.is_file(), f"missing Phase B module: {path}"


def test_phase_b_router_short_and_long_threshold() -> None:
    from backend.config import Settings

    settings = Settings(_env_file=None, ingest_short_page_limit=25, ingest_route="auto")
    assert resolve_ingest_route(25, settings=settings) == IngestRouteKind.SHORT
    assert resolve_ingest_route(26, settings=settings) == IngestRouteKind.LONG


def test_phase_b_b4_mineru_backend_exposes_pipeline_entrypoint() -> None:
    """B4: mineru_backend CLI wrapper is importable and typed."""
    assert callable(run_mineru_pipeline)
    assert callable(is_mineru_available)


def test_phase_b_b5_merge_with_rules_field_priority() -> None:
    """B5: head_merge_rules prefers path-B over snippets."""
    from backend.ingest.head_candidates import HeadCandidate

    snippets = HeadCandidate(title="PyMuPDF Title", source="pymupdf")
    path_b = HeadCandidate(title="MinerU Title", source="mineru")
    merged = merge_with_rules(snippets, path_b, is_short=True)
    assert merged.title == "MinerU Title"
    assert merged.sources["title"] == "mineru"


def test_phase_b_benchmark_script_surface(benchmark_dual_route_module) -> None:
    """B3: benchmark_dual_route.py exports comparison API used by batch eval."""
    mod = benchmark_dual_route_module
    for name in (
        "run_paper_comparison",
        "build_benchmark_settings",
        "list_corpus_paper_ids",
        "merge_with_rules",
        "score_sections",
    ):
        assert hasattr(mod, name), f"benchmark script missing {name}"


def test_phase_b_benchmark_script_all_corpus_cli_flag() -> None:
    import subprocess

    result = subprocess.run(
        [sys.executable, str(BENCHMARK_SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0
    assert "--all-corpus" in result.stdout
    assert "--with-llm" in result.stdout
    assert "--compare-baseline" in result.stdout
    assert "--write-baseline" in result.stdout


def test_phase_b_benchmark_regression_module_surface(benchmark_regression_module) -> None:
    mod = benchmark_regression_module
    for name in (
        "load_baseline",
        "compare_report_to_baseline",
        "summarize_report",
        "build_baseline_from_report",
    ):
        assert hasattr(mod, name), f"benchmark_regression missing {name}"


def test_phase_b_pyproject_declares_mineru_optional_extra() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "mineru[pipeline]" in text
    assert '"six>=' in text or "six>=" in text


def test_phase_b3_batch_report_schema_when_present(benchmark_regression_module) -> None:
    """B3/T6: latest corpus-batch JSON (if present) matches baseline regression."""
    reports = sorted(BENCHMARK_REPORT_DIR.glob("corpus-batch-*.json"))
    if not reports:
        pytest.skip("无本地 benchmark 报告：先跑 scripts/benchmark_dual_route.py --all-corpus")

    payload = json.loads(reports[-1].read_text(encoding="utf-8"))
    assert "paper_ids" in payload
    assert "results" in payload
    assert len(payload["paper_ids"]) >= 1

    first_id = payload["paper_ids"][0]
    row = payload["results"][first_id]
    assert "pymupdf_sync" in row
    assert "dual_route_rules" in row
    pym = row["pymupdf_sync"]
    assert pym is not None
    assert "quality" in pym
    assert "total" in pym["quality"]

    baseline_path = REPO_ROOT / "tests" / "fixtures" / "benchmark" / "dual_rules_baseline.json"
    if baseline_path.is_file():
        result = benchmark_regression_module.compare_report_to_baseline(payload)
        assert result.ok, result.format_message()


def _load_benchmark_module():
    spec = importlib.util.spec_from_file_location("benchmark_dual_route_check", BENCHMARK_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_phase_b3_list_corpus_excludes_probe_pdfs() -> None:
    mod = _load_benchmark_module()
    ids = mod.list_corpus_paper_ids(all_corpus=True)
    if not ids:
        pytest.skip("data/corpus 无 PDF")
    assert all(not paper_id.startswith("_probe") for paper_id in ids)
    assert len(ids) >= 3
