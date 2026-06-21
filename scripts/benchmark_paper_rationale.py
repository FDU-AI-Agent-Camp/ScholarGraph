"""Generic rationale stress-test for any corpus text file.

Usage:
    uv run python scripts/benchmark_paper_rationale.py <path-to-txt> <paradigm> <paper-id>
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.agents.extractor import extract
from backend.schemas.paradigm import Paradigm


def _coverage(edges: list[dict], edge_type: str, field: str) -> tuple[int, int]:
    subset = [e for e in edges if e.get("type") == edge_type]
    filled = [e for e in subset if e.get(field)]
    return len(filled), len(subset)


async def main() -> None:
    if len(sys.argv) < 4:
        print("Usage: benchmark_paper_rationale.py <txt-path> <STEM|HSS> <paper-id>")
        sys.exit(1)

    text_path = Path(sys.argv[1])
    paradigm = Paradigm(sys.argv[2].upper())
    paper_id = sys.argv[3]

    text = text_path.read_text(encoding="utf-8")
    print(f"Input: {len(text):,} chars from {text_path.name}")

    start = time.monotonic()
    result = await extract(text, paradigm, paper_id=paper_id)
    elapsed = time.monotonic() - start

    graph = result.graph
    edges = [e.model_dump(mode="json") for e in graph.edges]
    nodes = [n.model_dump(mode="json") for n in graph.nodes]

    print(f"\nElapsed: {elapsed:.1f}s ({elapsed / 60:.1f} min)")
    print(f"Nodes: {len(nodes)}")
    print(f"Edges: {len(edges)}")
    print(f"Warnings: {result.warnings}")

    core_types = {"SUPPORTS", "CONTRADICTS", "EXPLAINS"}
    all_types = sorted({e["type"] for e in edges})

    print("\n=== Rationale coverage by type ===")
    for etype in all_types:
        filled, total = _coverage(edges, etype, "rationale")
        marker = "*" if etype in core_types else " "
        print(f"  {marker}{etype:<18} {filled}/{total} ({filled / total * 100:.1f}%)")

    print("\n=== Source_span coverage by type ===")
    for etype in all_types:
        filled, total = _coverage(edges, etype, "source_span")
        marker = "*" if etype in core_types else " "
        print(f"  {marker}{etype:<18} {filled}/{total} ({filled / total * 100:.1f}%)")

    rationale_lengths = [len(e["rationale"]) for e in edges if e.get("rationale")]
    if rationale_lengths:
        print(
            f"\nRationale lengths: min={min(rationale_lengths)}, max={max(rationale_lengths)}, "
            f"avg={sum(rationale_lengths) / len(rationale_lengths):.1f}"
        )

    out_path = Path(f"data/benchmark_reports/{paper_id}_rationale_benchmark.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "paper_id": paper_id,
        "input_chars": len(text),
        "elapsed_seconds": elapsed,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "warnings": result.warnings,
        "rationale_coverage_by_type": {
            etype: _coverage(edges, etype, "rationale") for etype in all_types
        },
        "source_span_coverage_by_type": {
            etype: _coverage(edges, etype, "source_span") for etype in all_types
        },
        "rationale_length_stats": {
            "min": min(rationale_lengths) if rationale_lengths else None,
            "max": max(rationale_lengths) if rationale_lengths else None,
            "avg": round(sum(rationale_lengths) / len(rationale_lengths), 1) if rationale_lengths else None,
        },
        "sample_supports_edges": [e for e in edges if e["type"] == "SUPPORTS"][:3],
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved report to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
