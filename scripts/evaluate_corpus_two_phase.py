#!/usr/bin/env python3
"""Evaluate the updated two-phase extraction logic on all papers in data/corpus.

Usage (repo root):

    uv run python scripts/evaluate_corpus_two_phase.py

Output:
- Console markdown table with nodes/edges/time/warnings/status.
- JSON report under ``data/benchmark_reports/corpus_two_phase_eval_<ts>.json``.
"""

from __future__ import annotations

import argparse
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

if str(REPO_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(REPO_ROOT))


@dataclass
class EvalResult:
    """Metrics for one paper evaluated with two-phase extraction."""

    paper_id: str
    paradigm: str
    status: str  # success | fallback | error
    node_count: int = 0
    edge_count: int = 0
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
    if pid.startswith("stem-") or pid.startswith("_probe_synthetic_"):
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


def _ensure_two_phase() -> None:
    """Force two-phase extraction and clear settings cache."""
    os.environ["EXTRACT_TWO_PHASE_ENABLED"] = "true"

    from backend.config import get_settings
    from backend.llm.client import reset_llm_client_cache

    get_settings.cache_clear()
    reset_llm_client_cache()


async def _evaluate_paper(
    paper_id: str,
    *,
    max_chars: int,
    timeout_seconds: int,
) -> EvalResult:
    """Run two-phase extraction on one paper and collect metrics."""
    from backend.agents.extractor import extract
    from backend.config import get_settings
    from backend.schemas.paradigm import Paradigm

    _ensure_two_phase()
    settings = get_settings()
    settings.extract_max_input_chars = max_chars

    paradigm = Paradigm(_infer_paradigm(paper_id))
    result = EvalResult(paper_id=paper_id, paradigm=paradigm.value, status="error")

    full_text = await _load_full_text(paper_id)
    result.input_chars = len(full_text)

    started = time.perf_counter()
    try:
        extract_result = await asyncio.wait_for(
            extract(full_text, paradigm, paper_id=paper_id),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        result.elapsed_seconds = time.perf_counter() - started
        result.error = "Timeout"
        return result
    except Exception as exc:
        result.elapsed_seconds = time.perf_counter() - started
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    result.elapsed_seconds = time.perf_counter() - started
    result.node_count = len(extract_result.graph.nodes)
    result.edge_count = len(extract_result.graph.edges)
    result.warnings = extract_result.warnings
    result.status = "fallback" if any("extract_heuristic_fallback" in w for w in result.warnings) else "success"
    return result


def _print_table(results: list[EvalResult]) -> None:
    """Print markdown table to stdout."""
    headers = ["paper_id", "paradigm", "status", "nodes", "edges", "time", "warnings", "error"]
    rows: list[list[str]] = []
    for r in results:
        rows.append(
            [
                r.paper_id,
                r.paradigm,
                r.status,
                str(r.node_count),
                str(r.edge_count),
                f"{r.elapsed_seconds:.2f}s",
                ",".join(r.warnings) or "-",
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
    """Print aggregate summary."""
    total = len(results)
    success = sum(1 for r in results if r.status == "success")
    fallback = sum(1 for r in results if r.status == "fallback")
    errors = sum(1 for r in results if r.status == "error")
    ok_results = [r for r in results if r.status in {"success", "fallback"}]

    print("\n### Summary")
    print(f"- Total papers: {total}")
    print(f"- Success: {success}")
    print(f"- Fallback: {fallback}")
    print(f"- Error: {errors}")

    if ok_results:
        avg_time = sum(r.elapsed_seconds for r in ok_results) / len(ok_results)
        avg_nodes = sum(r.node_count for r in ok_results) / len(ok_results)
        avg_edges = sum(r.edge_count for r in ok_results) / len(ok_results)
        print(f"- Avg time (success/fallback): {avg_time:.2f}s")
        print(f"- Avg nodes/edges: {avg_nodes:.1f} / {avg_edges:.1f}")

    trunc_warnings = sum(
        1 for r in ok_results for w in r.warnings if "extract_field_truncated" in w
    )
    print(f"- Truncation warnings: {trunc_warnings}")


def _save_report(results: list[EvalResult], *, max_chars: int) -> Path:
    """Persist evaluation report as JSON."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = REPORT_DIR / f"corpus_two_phase_eval_{ts}.json"
    payload = {
        "meta": {
            "evaluated_at": ts,
            "extract_two_phase_enabled": True,
            "max_chars": max_chars,
            "total_papers": len(results),
        },
        "results": [asdict(r) for r in results],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate two-phase extraction on all corpus papers.")
    parser.add_argument("--max-chars", type=int, default=20_000, help="Max chars per paper (default: 20000).")
    parser.add_argument("--timeout", type=int, default=300, help="Per-paper timeout seconds (default: 300).")
    parser.add_argument("--papers", nargs="+", default=None, help="Override paper ids to evaluate.")
    args = parser.parse_args(argv)

    paper_ids = args.papers or _discover_papers()
    print(f"Evaluating {len(paper_ids)} papers from {CORPUS_DIR} (two-phase, max_chars={args.max_chars})")

    results: list[EvalResult] = []
    for pid in paper_ids:
        print(f"\n[{pid}] starting...", flush=True)
        result = await _evaluate_paper(pid, max_chars=args.max_chars, timeout_seconds=args.timeout)
        results.append(result)
        print(
            f"[{pid}] {result.status}: {result.node_count} nodes, {result.edge_count} edges, "
            f"{result.elapsed_seconds:.2f}s",
            flush=True,
        )
        if result.error:
            print(f"[{pid}] error: {result.error}", flush=True)

    _print_table(results)
    _print_summary(results)

    report_path = _save_report(results, max_chars=args.max_chars)
    print(f"\nReport saved to: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
