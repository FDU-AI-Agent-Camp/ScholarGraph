"""Dry-run script for edge rationale enrichment (Phase 1).

Reads a sample text file, runs the short-paper extraction path, and reports:
- Total edges produced
- Rationale coverage by edge type
- Source_span coverage by edge type
- Average rationale length
- Sample SUPPORTS edges with rationale
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.agents.extractor import extract_graph_only
from backend.schemas.paradigm import Paradigm

SAMPLE_TEXT_PATH = Path("data/corpus/stem-001.txt")
SAMPLE_LIMIT_CHARS = 6000


def _coverage(edges: list[dict], edge_type: str, field: str) -> tuple[int, int]:
    subset = [e for e in edges if e.get("type") == edge_type]
    filled = [e for e in subset if e.get(field)]
    return len(filled), len(subset)


def main() -> None:
    text = SAMPLE_TEXT_PATH.read_text(encoding="utf-8")[:SAMPLE_LIMIT_CHARS]
    print(f"Dry-run input: {len(text)} chars from {SAMPLE_TEXT_PATH.name}")

    graph = asyncio.run(extract_graph_only(text, Paradigm.STEM, paper_id="dry-run-stem-001"))

    edges = [e.model_dump(mode="json") for e in graph.edges]
    nodes = [n.model_dump(mode="json") for n in graph.nodes]

    print(f"\nNodes: {len(nodes)}")
    print(f"Edges: {len(edges)}")

    core_types = {"SUPPORTS", "CONTRADICTS", "EXPLAINS"}
    all_types = sorted({e["type"] for e in edges})

    print("\n=== Rationale coverage by type ===")
    for etype in all_types:
        filled, total = _coverage(edges, etype, "rationale")
        marker = "*" if etype in core_types else " "
        print(f"  {marker}{etype:<15} {filled}/{total} ({filled / total * 100:.1f}%)")

    print("\n=== Source_span coverage by type ===")
    for etype in all_types:
        filled, total = _coverage(edges, etype, "source_span")
        marker = "*" if etype in core_types else " "
        print(f"  {marker}{etype:<15} {filled}/{total} ({filled / total * 100:.1f}%)")

    rationale_lengths = [len(e["rationale"]) for e in edges if e.get("rationale")]
    if rationale_lengths:
        avg_length = sum(rationale_lengths) / len(rationale_lengths)
        print(
            f"\nRationale lengths: min={min(rationale_lengths)}, max={max(rationale_lengths)}, "
            f"avg={avg_length:.1f}"
        )

    print("\n=== Sample SUPPORTS edges ===")
    for e in [e for e in edges if e["type"] == "SUPPORTS"][:3]:
        print(json.dumps(e, ensure_ascii=False, indent=2))

    out_path = Path("data/tmp-test-graphs/dry_run_stem_001.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    print(f"\nSaved full graph to {out_path}")


if __name__ == "__main__":
    main()
