# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Stress test: full chunked two-phase extraction on hss-002 (≈460k chars).

Reports:
- Total elapsed time
- Final node/edge counts
- Rationale and source_span coverage by edge type
- Average rationale length
- Extract warnings and fallback status
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TEXT_PATH = Path("data/corpus/hss-002.txt")
PAPER_ID = "benchmark-hss-002-rationale"


def _coverage(edges: list[dict], edge_type: str, field: str) -> tuple[int, int]:
    subset = [e for e in edges if e.get("type") == edge_type]
    filled = [e for e in subset if e.get(field)]
    return len(filled), len(subset)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from backend.agents.extractor import extract
    from backend.schemas.paradigm import Paradigm

    text = TEXT_PATH.read_text(encoding="utf-8")
    print(f"Input: {len(text):,} chars from {TEXT_PATH.name}")

    start = time.monotonic()
    result = await extract(text, Paradigm.HSS, paper_id=PAPER_ID)
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

    out_path = Path("data/benchmark_reports/hss002_rationale_benchmark.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "paper_id": PAPER_ID,
        "input_chars": len(text),
        "elapsed_seconds": elapsed,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "warnings": result.warnings,
        "rationale_coverage_by_type": {etype: _coverage(edges, etype, "rationale") for etype in all_types},
        "source_span_coverage_by_type": {etype: _coverage(edges, etype, "source_span") for etype in all_types},
        "rationale_length_stats": {
            "min": min(rationale_lengths) if rationale_lengths else None,
            "max": max(rationale_lengths) if rationale_lengths else None,
            "avg": sum(rationale_lengths) / len(rationale_lengths) if rationale_lengths else None,
        },
        "sample_supports_edges": [e for e in edges if e["type"] == "SUPPORTS"][:3],
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved report to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
