#!/usr/bin/env python3
"""
双文共同体巡检 CLI（BE-4）。

在仓库根目录执行::

    uv run python scripts/run_patrol.py --seed-demo-graphs
    uv run python scripts/run_patrol.py --paper-ids hss-001,hss-002 --mode lens_clash

``--seed-demo-graphs`` 向 ``GRAPH_DATA_DIR`` 写入 ``docs/v1/eval/patrol_samples.md`` 中的评测图谱。

退出码：0 成功；1 巡检失败（PatrolError）；2 参数错误。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from backend.config import get_settings
from backend.graph.store import GraphStore
from backend.patrol.errors import PatrolError
from backend.patrol.samples import CORPUS_HSS_PAPER_IDS, seed_corpus_patrol_graphs
from backend.patrol.service import run_patrol
from backend.schemas.patrol import PatrolMode, PatrolReport

EXIT_SUCCESS = 0
EXIT_PATROL_FAILED = 1
EXIT_USAGE_ERROR = 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 ScholarGraph 双文巡检（Lens Clash 等）")
    parser.add_argument(
        "--paper-ids",
        default=",".join(CORPUS_HSS_PAPER_IDS),
        help="逗号分隔的两篇 paper_id（默认 hss-001,hss-002）",
    )
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in PatrolMode],
        default=PatrolMode.LENS_CLASH.value,
        help="巡检模式（V1 默认 lens_clash）",
    )
    parser.add_argument(
        "--graph-dir",
        type=Path,
        default=None,
        help="图谱目录（默认使用环境变量 GRAPH_DATA_DIR）",
    )
    parser.add_argument(
        "--seed-demo-graphs",
        action="store_true",
        help="运行前写入 patrol_samples 评测图谱（开发冒烟用）",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="单行 JSON 输出",
    )
    return parser.parse_args(argv)


def resolve_paper_ids(raw: str) -> list[str]:
    paper_ids = [part.strip() for part in raw.split(",") if part.strip()]
    if len(paper_ids) != 2:
        msg = f"--paper-ids 须恰好 2 篇，当前为 {len(paper_ids)} 篇"
        raise ValueError(msg)
    return paper_ids


def resolve_graph_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    settings = get_settings()
    return Path(settings.graph_data_dir).resolve()


async def execute_patrol(
    paper_ids: list[str],
    mode: PatrolMode,
    *,
    graph_dir: Path,
    seed_demo_graphs: bool,
) -> PatrolReport:
    graph_dir.mkdir(parents=True, exist_ok=True)
    if seed_demo_graphs:
        seed_corpus_patrol_graphs(graph_dir)
    store = GraphStore(base_dir=graph_dir)
    return await run_patrol(paper_ids, mode, store=store)


def print_report(report: PatrolReport, *, compact: bool) -> None:
    payload = report.model_dump(mode="json")
    if compact:
        print(json.dumps(payload, ensure_ascii=False))
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


async def async_main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        paper_ids = resolve_paper_ids(args.paper_ids)
        mode = PatrolMode(args.mode)
        graph_dir = resolve_graph_dir(args.graph_dir)
    except (argparse.ArgumentError, ValueError) as exc:
        print(f"参数错误: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    try:
        report = await execute_patrol(
            paper_ids,
            mode,
            graph_dir=graph_dir,
            seed_demo_graphs=args.seed_demo_graphs,
        )
    except PatrolError as exc:
        print(f"[{exc.code}] {exc.message}", file=sys.stderr)
        return EXIT_PATROL_FAILED

    print_report(report, compact=args.compact)
    return EXIT_SUCCESS


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
