#!/usr/bin/env python3
"""Run the latest extraction pipeline on every corpus paper and report quality.

Usage (repo root)::

    uv run python scripts/evaluate_corpus_quality_full.py

Output:
- Console markdown table with nodes/edges/warnings/quality/time/status.
- JSON report under ``data/benchmark_reports/corpus_quality_eval_<ts>.json``.
- Per-paper graph JSON under ``data/benchmark_reports/corpus_graphs/<paper_id>.json``.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = REPO_ROOT / "data" / "corpus"
REPORT_DIR = REPO_ROOT / "data" / "benchmark_reports"
GRAPH_DIR = REPORT_DIR / "corpus_graphs"

# Keep ingest head artefacts away from the default fixture graphs used by tests.
os.environ.setdefault("GRAPH_DATA_DIR", str(GRAPH_DIR))

if str(REPO_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(REPO_ROOT))


def _ensure_two_phase() -> None:
    """Force two-phase extraction and clear settings cache."""
    os.environ["EXTRACT_TWO_PHASE_ENABLED"] = "true"

    from backend.config import get_settings
    from backend.llm.client import reset_llm_client_cache

    get_settings.cache_clear()
    reset_llm_client_cache()


@dataclass
class EvalResult:
    """Metrics for one paper evaluated with the latest extraction + quality gate."""

    paper_id: str
    paradigm: str
    status: str  # success | fallback | timeout | error
    node_count: int = 0
    edge_count: int = 0
    supports_rationale_coverage: float = 0.0
    isolated_node_ratio: float = 0.0
    generic_edge_ratio: float = 0.0
    quality_gate_passed: bool = False
    quality_gate_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    error: str | None = None
    input_chars: int = 0


def _discover_papers() -> list[str]:
    """Return unique paper ids found in ``data/corpus`` (PDF or TXT only)."""
    if not CORPUS_DIR.is_dir():
        raise FileNotFoundError(f"Corpus directory not found: {CORPUS_DIR}")
    names = {
        path.stem
        for path in CORPUS_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in {".pdf", ".txt"} and not path.name.startswith(".")
    }
    return sorted(names)


def _infer_paradigm(paper_id: str) -> str:
    """Infer paradigm from paper id prefix."""
    pid = paper_id.lower()
    if pid.startswith("hss-"):
        return "HSS"
    if pid.startswith("stem-") or pid.startswith("_probe_synthetic_") or pid.startswith("_debug_"):
        return "STEM"
    raise ValueError(f"Cannot infer paradigm from paper_id: {paper_id}")


async def _load_full_text(paper_id: str) -> str:
    """Prefer ``.txt``; otherwise parse ``.pdf``."""
    txt_path = CORPUS_DIR / f"{paper_id}.txt"
    if txt_path.is_file():
        return txt_path.read_text(encoding="utf-8")

    pdf_path = CORPUS_DIR / f"{paper_id}.pdf"
    if pdf_path.is_file():
        from backend.ingest.pdf import ingest_pdf

        result = await ingest_pdf(pdf_path)
        return result["full_text"]

    raise FileNotFoundError(f"No corpus file found for {paper_id}")


async def _evaluate_paper(
    paper_id: str,
    *,
    max_chars: int,
    timeout_seconds: int,
) -> EvalResult:
    """Run extraction on one paper and collect quality metrics."""
    from backend.agents.extractor import extract
    from backend.config import get_settings
    from backend.graph.quality_gate import (
        evaluate_graph_quality,
        generic_edge_ratio,
        isolated_node_ratio,
        supports_rationale_coverage,
    )
    from backend.schemas.paradigm import Paradigm

    _ensure_two_phase()
    settings = get_settings()
    settings.extract_max_input_chars = max_chars

    paradigm = Paradigm(_infer_paradigm(paper_id))
    result = EvalResult(paper_id=paper_id, paradigm=paradigm.value, status="error")

    print(f"[{paper_id}] loading text...", flush=True)
    full_text = await _load_full_text(paper_id)
    result.input_chars = len(full_text)
    print(f"[{paper_id}] {len(full_text):,} chars -> extracting (timeout {timeout_seconds}s)...", flush=True)

    started = time.perf_counter()
    try:
        extract_result = await asyncio.wait_for(
            extract(full_text, paradigm, paper_id=paper_id),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        result.elapsed_seconds = time.perf_counter() - started
        result.error = "Timeout"
        result.status = "timeout"
        return result
    except Exception as exc:
        result.elapsed_seconds = time.perf_counter() - started
        result.error = f"{type(exc).__name__}: {exc}"
        result.status = "error"
        return result

    result.elapsed_seconds = time.perf_counter() - started
    graph = extract_result.graph
    result.node_count = len(graph.nodes)
    result.edge_count = len(graph.edges)
    result.warnings = extract_result.warnings
    result.status = "fallback" if any("extract_heuristic_fallback" in w for w in result.warnings) else "success"

    result.supports_rationale_coverage = supports_rationale_coverage(graph)
    result.isolated_node_ratio = isolated_node_ratio(graph)
    result.generic_edge_ratio = generic_edge_ratio(graph)
    passed, reasons = evaluate_graph_quality(
        graph,
        min_supports_rationale_coverage=settings.extract_min_supports_rationale_coverage,
        max_isolated_node_ratio=settings.extract_max_isolated_node_ratio,
        max_generic_edge_ratio=settings.extract_max_generic_edge_ratio,
    )
    result.quality_gate_passed = passed
    result.quality_gate_reasons = reasons

    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    (GRAPH_DIR / f"{paper_id}.json").write_text(
        graph.model_dump_json(indent=2),
        encoding="utf-8",
    )
    print(
        f"[{paper_id}] done: {result.node_count} nodes, {result.edge_count} edges, "
        f"gate={'PASS' if result.quality_gate_passed else 'FAIL'}, time={result.elapsed_seconds:.1f}s",
        flush=True,
    )
    return result


def _print_table(results: list[EvalResult]) -> None:
    """Print markdown table to stdout."""
    headers = [
        "paper_id",
        "paradigm",
        "status",
        "nodes",
        "edges",
        "supports_cov",
        "isolated",
        "generic",
        "gate",
        "time",
        "error",
    ]
    rows: list[list[str]] = []
    for r in results:
        rows.append(
            [
                r.paper_id,
                r.paradigm,
                r.status,
                str(r.node_count),
                str(r.edge_count),
                f"{r.supports_rationale_coverage:.0%}",
                f"{r.isolated_node_ratio:.1%}",
                f"{r.generic_edge_ratio:.1%}",
                "PASS" if r.quality_gate_passed else "FAIL",
                f"{r.elapsed_seconds:.1f}s",
                r.error or "-",
            ]
        )

    widths = [max(len(headers[i]), max((len(row[i]) for row in rows), default=0)) for i in range(len(headers))]

    def _fmt(row: list[str]) -> str:
        return " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    print("\n" + _fmt(headers))
    print(" | ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        print(_fmt(row))


def _print_summary(results: list[EvalResult]) -> None:
    """Print aggregate summary and quality gate analysis."""
    total = len(results)
    success = sum(1 for r in results if r.status == "success")
    fallback = sum(1 for r in results if r.status == "fallback")
    timeouts = sum(1 for r in results if r.status == "timeout")
    errors = sum(1 for r in results if r.status == "error")
    gate_pass = sum(1 for r in results if r.quality_gate_passed)
    gate_fail = total - gate_pass

    ok_results = [r for r in results if r.status in {"success", "fallback"}]

    print("\n### Summary")
    print(f"- Total papers: {total}")
    print(f"- Success: {success}")
    print(f"- Fallback: {fallback}")
    print(f"- Timeout: {timeouts}")
    print(f"- Error: {errors}")
    print(f"- Quality gate passed: {gate_pass}")
    print(f"- Quality gate failed: {gate_fail}")

    if ok_results:
        avg_time = sum(r.elapsed_seconds for r in ok_results) / len(ok_results)
        avg_nodes = sum(r.node_count for r in ok_results) / len(ok_results)
        avg_edges = sum(r.edge_count for r in ok_results) / len(ok_results)
        avg_cov = sum(r.supports_rationale_coverage for r in ok_results) / len(ok_results)
        avg_iso = sum(r.isolated_node_ratio for r in ok_results) / len(ok_results)
        avg_generic = sum(r.generic_edge_ratio for r in ok_results) / len(ok_results)
        print(f"- Avg time (success/fallback): {avg_time:.1f}s")
        print(f"- Avg nodes/edges: {avg_nodes:.1f} / {avg_edges:.1f}")
        print(f"- Avg SUPPORTS rationale coverage: {avg_cov:.1%}")
        print(f"- Avg isolated node ratio: {avg_iso:.1%}")
        print(f"- Avg generic edge ratio: {avg_generic:.1%}")

    if gate_fail:
        print("\n### Quality gate failures")
        for r in results:
            if not r.quality_gate_passed:
                print(f"- {r.paper_id}: {', '.join(r.quality_gate_reasons) or 'unknown'}")

    trunc_warnings = sum(1 for r in ok_results for w in r.warnings if "extract_field_truncated" in w)
    fallback_warnings = sum(1 for r in ok_results for w in r.warnings if "extract_heuristic_fallback" in w)
    print("\n### Warning counts")
    print(f"- Truncation warnings: {trunc_warnings}")
    print(f"- Heuristic fallback warnings: {fallback_warnings}")


def _save_report(results: list[EvalResult], *, max_chars: int, timeout_seconds: int) -> Path:
    """Persist evaluation report as JSON."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = REPORT_DIR / f"corpus_quality_eval_{ts}.json"
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "settings": {"max_chars": max_chars, "timeout_seconds": timeout_seconds},
        "papers": [asdict(r) for r in results],
        "summary": {
            "total": len(results),
            "success": sum(1 for r in results if r.status == "success"),
            "fallback": sum(1 for r in results if r.status == "fallback"),
            "timeout": sum(1 for r in results if r.status == "timeout"),
            "error": sum(1 for r in results if r.status == "error"),
            "quality_gate_passed": sum(1 for r in results if r.quality_gate_passed),
            "quality_gate_failed": sum(1 for r in results if not r.quality_gate_passed),
            "avg_generic_edge_ratio": sum(r.generic_edge_ratio for r in results) / max(1, len(results)),
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate latest extraction + quality gate on the full corpus.")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=20_000,
        help="Max chars passed to extraction per paper (default: 20000).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Per-extraction timeout in seconds (default: 600).",
    )
    parser.add_argument(
        "--only",
        type=str,
        default="",
        help="Comma-separated list of paper ids to evaluate (default: all).",
    )
    args = parser.parse_args(argv)

    paper_ids = _discover_papers()
    if args.only:
        allowed = {pid.strip() for pid in args.only.split(",")}
        paper_ids = [pid for pid in paper_ids if pid in allowed]
    print(f"Discovered {len(paper_ids)} corpus papers: {', '.join(paper_ids)}")

    async def _run_all() -> list[EvalResult]:
        return [await _evaluate_paper(pid, max_chars=args.max_chars, timeout_seconds=args.timeout) for pid in paper_ids]

    results = asyncio.run(_run_all())

    _print_table(results)
    _print_summary(results)

    report_path = _save_report(results, max_chars=args.max_chars, timeout_seconds=args.timeout)
    print(f"\nReport saved to {report_path}")
    print(f"Graphs saved to {GRAPH_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
