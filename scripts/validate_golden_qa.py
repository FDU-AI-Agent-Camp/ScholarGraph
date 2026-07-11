#!/usr/bin/env python
"""金标 QA ID 校验脚本 (V2 Phase 4).

遍历 ``data/qa_golden_set.json`` 中引用的 ``node_id`` 与 ``edge_id``，
校验是否仍存在于 ``data/graphs/`` 的图谱样本中。发现过期引用时以
非零退出码退出，提示重刷金标。

Usage (from repo root)::

    uv run python scripts/validate_golden_qa.py
    uv run python scripts/validate_golden_qa.py --graph-dir ./data/graphs
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.config import get_settings  # noqa: E402
from backend.graph.store import GraphStore  # noqa: E402

EXIT_SUCCESS = 0
EXIT_VALIDATION_FAILED = 1
EXIT_USAGE_ERROR = 2

_GOLDEN_SET_PATH = _REPO_ROOT / "data" / "qa_golden_set.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ScholarGraph 金标 QA ID 校验")
    parser.add_argument(
        "--golden-file",
        type=Path,
        default=_GOLDEN_SET_PATH,
        help="金标问题集路径 (default: data/qa_golden_set.json)",
    )
    parser.add_argument(
        "--graph-dir",
        type=Path,
        default=None,
        help="图谱目录（默认 GRAPH_DATA_DIR env）",
    )
    return parser.parse_args(argv)


def validate(args: argparse.Namespace) -> int:
    """Iterate golden QA items and verify referenced IDs still exist."""
    if not args.golden_file.is_file():
        print(f"[ERROR] 金标文件不存在: {args.golden_file}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    golden = json.loads(args.golden_file.read_text(encoding="utf-8"))
    items = golden.get("items", [])
    if not items:
        print("[ERROR] 金标文件中 items 为空", file=sys.stderr)
        return EXIT_USAGE_ERROR

    graph_dir = (args.graph_dir or Path(get_settings().graph_data_dir)).resolve()
    graph_dir.mkdir(parents=True, exist_ok=True)
    os.environ["GRAPH_DATA_DIR"] = str(graph_dir)
    get_settings.cache_clear()

    store = GraphStore(base_dir=graph_dir)
    all_valid = True

    # Collect all referenced paper_ids.
    paper_ids: set[str] = set()
    for item in items:
        pid = item.get("paper_id", "")
        if pid:
            paper_ids.add(pid)

    # Pre-load graphs.
    graphs: dict[str, object] = {}
    for pid in paper_ids:
        graph = store.load(pid)
        if graph is None:
            print(f"[WARN] 图谱未就绪: {pid} — 跳过该校验", file=sys.stderr)
            graphs[pid] = None
        else:
            graphs[pid] = graph
            node_ids = {n.id for n in graph.nodes}
            edge_ids = {e.id for e in graph.edges}
            print(f"[INFO] {pid}: {len(node_ids)} nodes, {len(edge_ids)} edges loaded")

    for idx, item in enumerate(items, start=1):
        question = item.get("question", f"item-{idx}")[:60]
        paper_id = item.get("paper_id", "")
        gold = item.get("gold", {})

        graph = graphs.get(paper_id)
        if graph is None:
            print(f"  [{idx}] [SKIP] {question} — paper {paper_id} not found")
            continue

        node_ids_in_graph = {n.id for n in graph.nodes}
        edge_ids_in_graph = {e.id for e in graph.edges}

        # Check nodes.
        for node_id in gold.get("nodes", []):
            if node_id not in node_ids_in_graph:
                print(
                    f"  [{idx}] ❌  FAIL: node_id={node_id!r} 不在 {paper_id} 图谱中 (question: {question})",
                    file=sys.stderr,
                )
                all_valid = False

        # Check edges.
        for edge_id in gold.get("edges", []):
            if edge_id not in edge_ids_in_graph:
                print(
                    f"  [{idx}] ❌  FAIL: edge_id={edge_id!r} 不在 {paper_id} 图谱中 (question: {question})",
                    file=sys.stderr,
                )
                all_valid = False

    if all_valid:
        print(f"\n[OK] 所有 {len(items)} 个金标问题的 ID 引用均有效。")
        return EXIT_SUCCESS

    print(
        f"\n[FAIL] 发现过期 ID 引用，请更新 {args.golden_file} 中的 nodes/edges 字段后重新运行。",
        file=sys.stderr,
    )
    return EXIT_VALIDATION_FAILED


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return validate(args)


if __name__ == "__main__":
    raise SystemExit(main())
