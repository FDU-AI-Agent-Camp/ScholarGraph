"""Run the latest extraction pipeline over the six benchmark corpora.

Outputs final graphs to ``data/graphs/{paper_id}.json`` and a metrics report.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from backend.agents.extract_heuristic import extract_title
from backend.agents.extractor import _extract_two_phase
from backend.config import Settings
from backend.graph.store import GraphStore
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = REPO_ROOT / "data" / "corpus"
GRAPH_DIR = REPO_ROOT / "data" / "graphs"
REPORT_PATH = REPO_ROOT / "data" / "benchmark_reports" / "corpus_six_report.json"

PAPER_IDS = ["hss-001", "hss-002", "hss-003", "stem-001", "stem-002", "stem-003"]


def _detect_paradigm(paper_id: str) -> Paradigm:
    if paper_id.startswith("hss"):
        return Paradigm.HSS
    if paper_id.startswith("stem"):
        return Paradigm.STEM
    raise ValueError(f"unknown paper prefix: {paper_id}")


def _compute_components(graph: UnifiedPaperGraph) -> tuple[int, int]:
    node_ids = {node.id for node in graph.nodes}
    adj: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for edge in graph.edges:
        if edge.source in node_ids and edge.target in node_ids:
            adj[edge.source].add(edge.target)
            adj[edge.target].add(edge.source)

    visited: set[str] = set()
    components: list[set[str]] = []
    stack: list[str] = []
    for node_id in node_ids:
        if node_id in visited:
            continue
        stack.append(node_id)
        visited.add(node_id)
        component: set[str] = set()
        while stack:
            current = stack.pop()
            component.add(current)
            for neighbor in adj[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        components.append(component)

    components.sort(key=len, reverse=True)
    largest = len(components[0]) if components else 0
    return len(components), largest


def _node_type_distribution(graph: UnifiedPaperGraph) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for node in graph.nodes:
        counts[node.type] += 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


async def _run_one(paper_id: str, settings: Settings) -> dict:
    logger.info("start_extraction", extra={"paper_id": paper_id})
    text_path = CORPUS_DIR / f"{paper_id}.txt"
    if not text_path.is_file():
        raise FileNotFoundError(f"missing corpus text: {text_path}")

    full_text = text_path.read_text(encoding="utf-8")
    paradigm = _detect_paradigm(paper_id)
    title = extract_title(full_text)

    started_at = datetime.now(UTC)
    result = await _extract_two_phase(
        full_text,
        paradigm,
        paper_id=paper_id,
        title=title,
        head_context=None,
        settings=settings,
    )
    elapsed_s = (datetime.now(UTC) - started_at).total_seconds()

    graph = result.graph
    GraphStore(base_dir=GRAPH_DIR).save(graph)

    components, largest_component = _compute_components(graph)
    metrics = {
        "paper_id": paper_id,
        "paradigm": paradigm.value,
        "title": title,
        "chars": len(full_text),
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "components": components,
        "largest_component": largest_component,
        "largest_component_pct": round(largest_component / len(graph.nodes) * 100, 2) if graph.nodes else 0,
        "elapsed_s": elapsed_s,
        "warnings": result.warnings,
        "node_types": _node_type_distribution(graph),
    }
    logger.info(
        "extraction_complete",
        extra={
            "paper_id": paper_id,
            "nodes": metrics["nodes"],
            "edges": metrics["edges"],
            "components": components,
            "elapsed_s": elapsed_s,
        },
    )
    return metrics


async def main() -> int:
    settings = Settings()
    if settings.llm_mode != "live":
        logger.warning("LLM_MODE is not live; results will be mock/heuristic only")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    errors: list[dict] = []

    for paper_id in PAPER_IDS:
        try:
            metrics = await _run_one(paper_id, settings)
            results.append(metrics)
        except Exception as exc:
            logger.exception("extraction_failed", extra={"paper_id": paper_id})
            errors.append({"paper_id": paper_id, "error": str(exc)})

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "llm_mode": settings.llm_mode,
        "embedding_model": settings.embedding_model,
        "semantic_clustering_enabled": settings.semantic_clustering_enabled,
        "semantic_similarity_threshold": settings.semantic_similarity_threshold_effective,
        "semantic_knn_threshold": settings.semantic_knn_threshold_effective,
        "results": results,
        "errors": errors,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("report_written", extra={"path": str(REPORT_PATH)})
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
