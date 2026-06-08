"""Dual-route benchmark: orchestration unit tests + optional live MinerU comparison."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.config import Settings
from backend.ingest.head_candidates import HeadCandidate
from backend.ingest.mineru_backend import is_mineru_available
from backend.ingest.router import get_pdf_page_count, is_short_pdf
from tests.ingest.conftest import CORPUS_DIR

BENCHMARK_SHORT_PAPER_ID = "stem-001"
EXPECTED_PATH_KEYS = (
    "pymupdf_sync",
    "grobid_crf",
    "mineru_pipeline",
    "dual_route_rules",
    "dual_route_llm",
)


def _corpus_pdf(paper_id: str) -> Path:
    return CORPUS_DIR / f"{paper_id}.pdf"


def _benchmark_settings() -> Settings:
    return Settings(
        _env_file=None,
        llm_mode="mock",
        ingest_head_llm_enabled=False,
        ingest_mineru_enabled=True,
        ingest_mineru_model_source="modelscope",
        ingest_mineru_timeout_seconds=600,
        ingest_short_page_limit=25,
        ingest_route="auto",
    )


@pytest.mark.asyncio
async def test_paper_comparison_orchestration_mocked(
    benchmark_dual_route_module,
    structured_stem_pdf: Path,
) -> None:
    """One-PDF comparison set wires all paths without calling real MinerU/GROBID."""
    mod = benchmark_dual_route_module
    pym_result = mod.PathResult(
        label="pymupdf_sync",
        elapsed_seconds=0.01,
        sections=mod.parse_classifier_sections("Title: Mock\nAbstract: " + "x" * 80),
        quality=mod.QualityScore(total=2, title=True, abstract=True, keywords=False, intro=False),
    )
    mineru_result = mod.PathResult(
        label="mineru_pipeline",
        elapsed_seconds=0.02,
        sections=mod.parse_classifier_sections("Title: MinerU Title\nIntro: " + "y" * 40),
        quality=mod.QualityScore(total=2, title=True, abstract=False, keywords=False, intro=True),
    )
    settings = _benchmark_settings()

    with (
        patch.object(mod, "run_pymupdf_sync", new_callable=AsyncMock, return_value=pym_result),
        patch.object(mod, "run_grobid_path", new_callable=AsyncMock, return_value=None),
        patch.object(mod, "run_mineru_path", return_value=mineru_result),
    ):
        row = await mod.run_paper_comparison(structured_stem_pdf, settings, with_llm=False)

    assert set(row.keys()) == set(EXPECTED_PATH_KEYS)
    assert row["pymupdf_sync"] is pym_result
    assert row["mineru_pipeline"] is mineru_result
    assert row["grobid_crf"] is None
    assert row["dual_route_llm"] is None

    dual = row["dual_route_rules"]
    assert dual is not None
    assert dual.label == "dual_route_rules"
    assert dual.sections.title.strip()
    assert "mineru" in dual.sources.values()


@pytest.mark.asyncio
async def test_paper_comparison_short_pdf_uses_mineru_in_dual_rules(
    benchmark_dual_route_module,
    structured_stem_pdf: Path,
) -> None:
    """Short PDF dual(rules) should consume mocked MinerU path-B."""
    mod = benchmark_dual_route_module
    settings = _benchmark_settings()
    snippets = mod.build_pymupdf_head_candidate(structured_stem_pdf)
    mineru_candidate = HeadCandidate(
        title="MinerU Canonical Title",
        abstract="MinerU abstract " + "a" * 80,
        keywords="kw1, kw2",
        intro="MinerU intro " + "i" * 40,
        source="mineru",
    )
    mineru_result = mod.PathResult(
        label="mineru_pipeline",
        elapsed_seconds=0.05,
        sections=mod.sections_from_head(mineru_candidate),
        quality=mod.score_sections(mod.sections_from_head(mineru_candidate), paper_id=structured_stem_pdf.stem),
    )
    pym_result = mod.PathResult(
        label="pymupdf_sync",
        elapsed_seconds=0.01,
        sections=mod.sections_from_head(snippets),
        quality=mod.score_sections(mod.sections_from_head(snippets), paper_id=structured_stem_pdf.stem),
    )

    with (
        patch.object(mod, "run_pymupdf_sync", new_callable=AsyncMock, return_value=pym_result),
        patch.object(mod, "run_grobid_path", new_callable=AsyncMock, return_value=None),
        patch.object(mod, "run_mineru_path", return_value=mineru_result),
    ):
        row = await mod.run_paper_comparison(structured_stem_pdf, settings, with_llm=False)

    dual = row["dual_route_rules"]
    assert dual is not None
    assert dual.sections.title == "MinerU Canonical Title"
    assert dual.sources.get("title") == "mineru"


def test_benchmark_script_help_exits_zero(benchmark_dual_route_module) -> None:
    import subprocess
    import sys

    from tests.conftest import BENCHMARK_DUAL_ROUTE_SCRIPT, REPO_ROOT

    result = subprocess.run(
        [sys.executable, str(BENCHMARK_DUAL_ROUTE_SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0
    assert "--with-llm" in result.stdout


@pytest.mark.live_mineru
@pytest.mark.asyncio
async def test_live_single_pdf_comparison_experiment(benchmark_dual_route_module) -> None:
    """
    End-to-end one-PDF benchmark (§2.1): PyMuPDF + MinerU + dual(rules).

    Run explicitly: ``uv run pytest tests/ingest/test_benchmark_dual_route.py -m live_mineru -v``
    Requires: ``uv sync --extra mineru``, ``data/corpus/stem-001.pdf``.
    """
    if not is_mineru_available():
        pytest.skip("MinerU 未安装：uv sync --extra mineru")

    pdf_path = _corpus_pdf(BENCHMARK_SHORT_PAPER_ID)
    if not pdf_path.is_file():
        pytest.skip(f"语料 PDF 未就位: {pdf_path}")

    mod = benchmark_dual_route_module
    settings = mod.build_benchmark_settings(with_llm=False)
    page_count = get_pdf_page_count(pdf_path)
    assert is_short_pdf(page_count, settings=settings), "stem-001 应为短档 MinerU 路由"

    row = await mod.run_paper_comparison(pdf_path, settings, with_llm=False)

    assert set(row.keys()) == set(EXPECTED_PATH_KEYS)

    pym = row["pymupdf_sync"]
    assert pym is not None
    assert pym.elapsed_seconds >= 0
    assert pym.sections.title.strip() or pym.sections.intro.strip()
    assert 0 <= pym.quality.total <= 4

    mineru = row["mineru_pipeline"]
    assert mineru is not None, "MinerU path-B 应成功返回 HeadCandidate"
    assert mineru.elapsed_seconds > 0
    assert mineru.sections.title.strip() or mineru.sections.intro.strip(), "MinerU 应至少抽取 title 或 intro"
    assert 0 <= mineru.quality.total <= 4

    dual = row["dual_route_rules"]
    assert dual is not None
    assert dual.sections.title.strip()
    assert dual.sources, "dual(rules) 应记录字段来源"
    assert any(source == "mineru" for source in dual.sources.values()), "短档 dual(rules) 应合并 MinerU path-B"
    assert 0 <= dual.quality.total <= 4

    # GROBID 可能离线；短档对比实验不依赖 grobid_crf 成功
    assert row["dual_route_llm"] is None
