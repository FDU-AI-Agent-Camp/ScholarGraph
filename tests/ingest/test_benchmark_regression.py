# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""T6: benchmark JSON regression baseline (dual rules quality)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "benchmark" / "dual_rules_baseline.json"
BENCHMARK_REGRESSION_SCRIPT = REPO_ROOT / "scripts" / "benchmark_regression.py"
BENCHMARK_REPORT_DIR = REPO_ROOT / "data" / "benchmark_reports"


def _load_regression_module():
    spec = importlib.util.spec_from_file_location("benchmark_regression", BENCHMARK_REGRESSION_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def benchmark_regression_module():
    return _load_regression_module()


def test_dual_rules_baseline_fixture_present() -> None:
    assert BASELINE_PATH.is_file(), f"missing committed baseline: {BASELINE_PATH}"


def test_dual_rules_baseline_schema_and_phase_d_totals(benchmark_regression_module) -> None:
    mod = benchmark_regression_module
    baseline = mod.load_baseline(BASELINE_PATH)

    assert baseline["baseline_id"] == "phase-d-dual-rules"
    assert len(baseline["paper_ids"]) == 17
    totals = baseline["totals"]
    assert totals["dual_route_rules"] == 46
    assert totals["pymupdf_sync"] == 33
    assert totals["path_b"] == 42
    assert totals["max"] == 68

    for paper_id in baseline["paper_ids"]:
        quality = baseline["papers"][paper_id]["quality"]
        dual = quality["dual_route_rules"]
        assert dual >= quality["pymupdf_sync"]
        assert dual >= quality["path_b"]


def test_compare_report_to_baseline_self_match(benchmark_regression_module) -> None:
    mod = benchmark_regression_module
    baseline = mod.load_baseline(BASELINE_PATH)

    synthetic_report = {
        "paper_ids": baseline["paper_ids"],
        "results": {},
    }
    for paper_id in baseline["paper_ids"]:
        entry = baseline["papers"][paper_id]
        pages = entry.get("pages")
        short = isinstance(pages, int) and pages <= 25
        path_b_key = "mineru_pipeline" if short else "grobid_crf"
        quality = entry["quality"]

        def _row(score: int) -> dict:
            return {"quality": {"total": score, "title": True, "abstract": True, "keywords": True, "intro": True}}

        synthetic_report["results"][paper_id] = {
            "pages": pages,
            "pymupdf_sync": _row(quality["pymupdf_sync"]),
            path_b_key: _row(quality["path_b"]),
            "dual_route_rules": _row(quality["dual_route_rules"]),
        }

    result = mod.compare_report_to_baseline(synthetic_report, baseline)
    assert result.ok, result.format_message()


def test_validate_baseline_rejects_bad_schema_version(benchmark_regression_module) -> None:
    mod = benchmark_regression_module
    with pytest.raises(ValueError, match="schema_version"):
        mod.validate_baseline({"schema_version": 99})


def test_validate_baseline_rejects_monotonicity_violation(benchmark_regression_module) -> None:
    mod = benchmark_regression_module
    payload = {
        "schema_version": mod.BASELINE_SCHEMA_VERSION,
        "baseline_id": "bad",
        "paper_ids": ["x"],
        "totals": {"dual_route_rules": 1, "pymupdf_sync": 2, "path_b": 2, "max": 4},
        "constraints": {"dual_gte_pymupdf": True, "dual_gte_path_b": True},
        "papers": {
            "x": {
                "pages": 10,
                "route": "short",
                "quality": {"pymupdf_sync": 3, "path_b": 2, "dual_route_rules": 1},
            },
        },
    }
    with pytest.raises(ValueError, match="dual_route_rules"):
        mod.validate_baseline(payload)


def test_summarize_report_uses_mineru_for_short_and_grobid_for_long(benchmark_regression_module) -> None:
    mod = benchmark_regression_module
    report = {
        "paper_ids": ["short-p", "long-p"],
        "results": {
            "short-p": {
                "pages": 8,
                "pymupdf_sync": {"quality": {"total": 2}},
                "mineru_pipeline": {"quality": {"total": 3}},
                "grobid_crf": {"quality": {"total": 0}},
                "dual_route_rules": {"quality": {"total": 3}},
            },
            "long-p": {
                "pages": 100,
                "pymupdf_sync": {"quality": {"total": 1}},
                "mineru_pipeline": {"quality": {"total": 4}},
                "grobid_crf": {"quality": {"total": 3}},
                "dual_route_rules": {"quality": {"total": 3}},
            },
        },
    }
    totals = mod.summarize_report(report)
    assert totals.pymupdf_sync == 3
    assert totals.path_b == 6
    assert totals.dual_route_rules == 6
    assert totals.max_total == 8


def test_compare_report_detects_regression(benchmark_regression_module) -> None:
    mod = benchmark_regression_module
    baseline = mod.load_baseline(BASELINE_PATH)
    regressed = {
        "paper_ids": baseline["paper_ids"],
        "results": {},
    }
    first_id = baseline["paper_ids"][0]
    entry = baseline["papers"][first_id]
    pages = entry["pages"]
    short = pages <= 25
    path_b_key = "mineru_pipeline" if short else "grobid_crf"
    quality = entry["quality"]

    def _row(score: int) -> dict:
        return {"quality": {"total": score}}

    for paper_id in baseline["paper_ids"]:
        if paper_id == first_id:
            regressed["results"][paper_id] = {
                "pages": pages,
                "pymupdf_sync": _row(quality["pymupdf_sync"]),
                path_b_key: _row(quality["path_b"]),
                "dual_route_rules": _row(max(0, quality["dual_route_rules"] - 1)),
            }
        else:
            e = baseline["papers"][paper_id]
            p = e["pages"]
            s = p <= 25
            pb = "mineru_pipeline" if s else "grobid_crf"
            q = e["quality"]
            regressed["results"][paper_id] = {
                "pages": p,
                "pymupdf_sync": _row(q["pymupdf_sync"]),
                pb: _row(q["path_b"]),
                "dual_route_rules": _row(q["dual_route_rules"]),
            }

    result = mod.compare_report_to_baseline(regressed, baseline)
    assert not result.ok
    assert any(diff.paper_id == first_id for diff in result.diffs)


def test_build_baseline_from_report_writes_valid_payload(benchmark_regression_module, tmp_path: Path) -> None:
    mod = benchmark_regression_module
    report = {
        "paper_ids": ["demo"],
        "generated_at": "2026-06-07T00:00:00Z",
        "results": {
            "demo": {
                "pages": 10,
                "pymupdf_sync": {"quality": {"total": 2}},
                "mineru_pipeline": {"quality": {"total": 3}},
                "dual_route_rules": {"quality": {"total": 3}},
            },
        },
    }
    payload = mod.build_baseline_from_report(report, baseline_id="demo", source_report="demo.json")
    out = mod.write_baseline(payload, tmp_path / "demo_baseline.json")
    restored = mod.load_baseline(out)
    assert restored["totals"]["dual_route_rules"] == 3


def test_latest_local_batch_report_matches_baseline_when_present(benchmark_regression_module) -> None:
    """Optional offline report: compare latest corpus-batch JSON to committed baseline."""
    reports = sorted(BENCHMARK_REPORT_DIR.glob("corpus-batch-*.json"))
    if not reports:
        pytest.skip("无本地 benchmark 报告：先跑 scripts/benchmark_dual_route.py --all-corpus")

    mod = benchmark_regression_module
    report = json.loads(reports[-1].read_text(encoding="utf-8"))
    result = mod.compare_report_to_baseline(report)
    assert result.ok, result.format_message()


@pytest.mark.live_benchmark
def test_live_all_corpus_matches_committed_baseline(benchmark_regression_module) -> None:
    """Full regression: rerun benchmark and compare to committed baseline.

    Run explicitly:
        uv run pytest tests/ingest/test_benchmark_regression.py -m live_benchmark -v
    """
    mod = benchmark_regression_module
    benchmark_mod_path = REPO_ROOT / "scripts" / "benchmark_dual_route.py"
    spec = importlib.util.spec_from_file_location("benchmark_dual_route_live", benchmark_mod_path)
    assert spec is not None and spec.loader is not None
    benchmark_mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = benchmark_mod
    spec.loader.exec_module(benchmark_mod)

    paper_ids = benchmark_mod.list_corpus_paper_ids(all_corpus=True)
    if len(paper_ids) < 17:
        pytest.skip("需要 data/corpus 17 篇 PDF（不含 _probe*）")

    import asyncio

    settings = benchmark_mod.build_benchmark_settings(with_llm=False)
    all_results: dict[str, dict] = {}
    for paper_id in paper_ids:
        pdf_path = benchmark_mod.CORPUS_DIR / f"{paper_id}.pdf"
        if not pdf_path.is_file():
            pytest.skip(f"missing PDF: {paper_id}")
        all_results[paper_id] = asyncio.run(
            benchmark_mod.run_paper_comparison(
                pdf_path,
                settings,
                with_llm=False,
                skip_mineru_on_long=True,
            )
        )

    report = {
        "paper_ids": list(paper_ids),
        "generated_at": "live-test",
        "results": {},
    }
    for paper_id, row in all_results.items():
        pdf = benchmark_mod.CORPUS_DIR / f"{paper_id}.pdf"
        pages = benchmark_mod.get_pdf_page_count(pdf)
        entry: dict = {"pages": pages}
        for key, result in row.items():
            if result is None:
                entry[key] = None
                continue
            from dataclasses import asdict

            entry[key] = {
                "quality": asdict(result.quality),
                "elapsed_seconds": result.elapsed_seconds,
            }
        report["results"][paper_id] = entry

    result = mod.compare_report_to_baseline(report)
    assert result.ok, result.format_message()
