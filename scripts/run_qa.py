#!/usr/bin/env python
# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Demo script: run multi-scale QA over a stored paper graph.

Usage (from repo root)::

    uv run python scripts/run_qa.py <paper_id> "<question>"
    uv run python scripts/run_qa.py --smoke-m2 --seed-demo-graph

Example::

    uv run python scripts/run_qa.py hss-001 "这篇论文的核心论点是什么？"
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Ensure repo root is on sys.path.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.config import get_settings  # noqa: E402
from backend.graph.qa import qa_stream  # noqa: E402
from backend.graph.qa_samples import M2_DEMO_PAPER_ID, M2_HSS_QUESTIONS, seed_m2_qa_graph  # noqa: E402
from backend.graph.store import GraphStore  # noqa: E402

EXIT_SUCCESS = 0
EXIT_QA_FAILED = 1
EXIT_USAGE_ERROR = 2


@dataclass(frozen=True, slots=True)
class QaRunResult:
    """Aggregated SSE outcome for one QA turn."""

    answer_text: str
    citations: list[dict[str, str]]
    error_code: str | None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ScholarGraph 单篇多尺度问答 CLI（M2 / A-09）")
    parser.add_argument("paper_id", nargs="?", help="论文 ID")
    parser.add_argument("question", nargs="?", help="用户问题")
    parser.add_argument(
        "--graph-dir",
        type=Path,
        default=None,
        help="图谱目录（默认 GRAPH_DATA_DIR）",
    )
    parser.add_argument(
        "--seed-demo-graph",
        action="store_true",
        help="运行前写入 M2 评测图谱（hss-001 fixture）",
    )
    parser.add_argument(
        "--smoke-m2",
        action="store_true",
        help="依次跑摘要/细节/验证三类 canonical 问题并校验 citation",
    )
    return parser.parse_args(argv)


def resolve_graph_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    return Path(get_settings().graph_data_dir).resolve()


def bind_graph_dir(graph_dir: Path) -> None:
    """Point ``qa_stream`` / ``GraphStore`` at *graph_dir* (CLI ``--graph-dir``)."""
    os.environ["GRAPH_DATA_DIR"] = str(graph_dir)
    get_settings.cache_clear()


async def run_single_qa(paper_id: str, question: str) -> QaRunResult:
    answer_parts: list[str] = []
    citations: list[dict[str, str]] = []
    error_code: str | None = None

    async for evt in qa_stream(paper_id, question):
        if evt.event == "message":
            answer_parts.append(evt.data["delta"])
        elif evt.event == "citation":
            citations.append(evt.data)
        elif evt.event == "error":
            error_code = evt.data["code"]
            print(f"\n[ERROR] {evt.data['code']}: {evt.data['message']}")
        elif evt.event == "done":
            print(f"\n\n[OK] answer_id = {evt.data.get('answer_id', '—')}")

    return QaRunResult("".join(answer_parts), citations, error_code)


async def print_qa_turn(paper_id: str, question: str) -> QaRunResult:
    print(f"paper_id : {paper_id}")
    print(f"question : {question}")
    print("-" * 60)
    try:
        return await run_single_qa(paper_id, question)
    except Exception as exc:
        print(f"\n[FATAL] Unhandled: {exc}")
        raise


def verify_citation(result: QaRunResult, graph_dir: Path, paper_id: str) -> bool:
    if result.error_code:
        return False
    if not result.citations:
        print("[FAIL] 缺少 citation 事件", file=sys.stderr)
        return False

    graph = GraphStore(base_dir=graph_dir).load(paper_id)
    if graph is None:
        print(f"[FAIL] 图谱不存在: {paper_id}", file=sys.stderr)
        return False

    node_index = {node.id: node for node in graph.nodes}
    for cite in result.citations:
        node_id = cite["node_id"]
        node = node_index.get(node_id)
        if node is None:
            print(f"[FAIL] citation 节点 {node_id!r} 不在图谱中", file=sys.stderr)
            return False
        if cite.get("label") != node.label:
            print(
                f"[FAIL] citation label 不匹配: {cite.get('label')!r} != {node.label!r}",
                file=sys.stderr,
            )
            return False
        print(f"  [OK] citation {node_id} -> {node.label} ({node.type})")
    return True


async def smoke_m2(graph_dir: Path, *, paper_id: str = M2_DEMO_PAPER_ID) -> int:
    print(f"[ScholarGraph M2 smoke] graph_dir={graph_dir} paper_id={paper_id}")
    failed = False
    for sample in M2_HSS_QUESTIONS:
        print()
        result = await print_qa_turn(paper_id, sample.question)
        ok = verify_citation(result, graph_dir, paper_id)
        if not ok:
            failed = True
            continue
        graph = GraphStore(base_dir=graph_dir).load(paper_id)
        assert graph is not None
        cited_node = next(n for n in graph.nodes if n.id == result.citations[0]["node_id"])
        if cited_node.type not in sample.expected_node_types:
            print(
                f"[FAIL] 尺度 {sample.scale} 期望节点类型 {sample.expected_node_types}，实际 {cited_node.type}",
                file=sys.stderr,
            )
            failed = True
        else:
            print(f"  [OK] 尺度 {sample.scale} -> {cited_node.type}")
    return EXIT_QA_FAILED if failed else EXIT_SUCCESS


async def main_async(args: argparse.Namespace) -> int:
    graph_dir = resolve_graph_dir(args.graph_dir)
    graph_dir.mkdir(parents=True, exist_ok=True)
    bind_graph_dir(graph_dir)
    if args.seed_demo_graph:
        seed_m2_qa_graph(graph_dir)

    if args.smoke_m2:
        return await smoke_m2(graph_dir)

    if not args.paper_id or not args.question:
        if args.seed_demo_graph:
            return EXIT_SUCCESS
        print("Usage: uv run python scripts/run_qa.py <paper_id> <question>", file=sys.stderr)
        print("       uv run python scripts/run_qa.py --smoke-m2 --seed-demo-graph", file=sys.stderr)
        return EXIT_USAGE_ERROR

    result = await print_qa_turn(args.paper_id, args.question)
    if result.error_code:
        return EXIT_QA_FAILED
    if not verify_citation(result, graph_dir, args.paper_id):
        return EXIT_QA_FAILED
    return EXIT_SUCCESS


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
