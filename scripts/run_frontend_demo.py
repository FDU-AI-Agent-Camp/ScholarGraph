#!/usr/bin/env python3
"""
浏览器全链路联调准备脚本（FE-11）。

在仓库根目录执行::

    uv run python scripts/run_frontend_demo.py

可选::

    uv run python scripts/run_frontend_demo.py --skip-seed
    uv run python scripts/run_frontend_demo.py --mode contradiction

默认会 seed 巡检评测图谱，并打印后端/前端启动命令与演示 URL 清单。
详细步骤见 ``docs/v1/eval/frontend-demo-path.md``。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_BASE = "http://localhost:5173"
BACKEND_BASE = "http://127.0.0.1:8000"

DEMO_URLS: list[tuple[str, str]] = [
    ("工作台", f"{FRONTEND_BASE}/"),
    ("文献库", f"{FRONTEND_BASE}/papers"),
    ("上传（文献库内嵌）", f"{FRONTEND_BASE}/papers"),
    ("详情 · ready", f"{FRONTEND_BASE}/papers/hss-001"),
    ("详情 · 失败态", f"{FRONTEND_BASE}/papers/hss-failed-001"),
    ("详情 · processing", f"{FRONTEND_BASE}/papers/hss-002"),
    ("图谱", f"{FRONTEND_BASE}/papers/hss-001/graph"),
    ("图谱 · 高亮节点", f"{FRONTEND_BASE}/papers/hss-001/graph?node=n_lens_a"),
    ("问答（详情页内嵌）", f"{FRONTEND_BASE}/papers/hss-001"),
    ("巡检", f"{FRONTEND_BASE}/patrol"),
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ScholarGraph 前端浏览器全链路联调准备")
    parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="跳过 patrol 评测图谱 seed",
    )
    parser.add_argument(
        "--mode",
        choices=["lens_clash", "contradiction", "method_overlap", "claim_evolution"],
        default="lens_clash",
        help="seed 后可选执行的 CLI 巡检模式（冒烟）",
    )
    parser.add_argument(
        "--no-stem-seed",
        action="store_true",
        help="仅 seed HSS 图谱（默认同时 seed stem-001/stem-002）",
    )
    parser.add_argument(
        "--smoke-all-patrol",
        action="store_true",
        help="seed 后依次冒烟四模式（lens_clash / contradiction / method_overlap / claim_evolution）",
    )
    parser.add_argument(
        "--smoke-patrol",
        action="store_true",
        help="seed 后额外执行 run_patrol.py CLI 冒烟",
    )
    return parser.parse_args(argv)


def run_seed(*, include_stem: bool = True) -> int:
    flag = "--seed-demo-graphs" if include_stem else "--seed-hss-demo"
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "run_patrol.py"), flag]
    print(">>", " ".join(cmd))
    completed = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    return completed.returncode


def run_patrol_smoke(mode: str) -> int:
    paper_ids = "stem-001,stem-002" if mode in {"method_overlap", "claim_evolution"} else "hss-001,hss-002"
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_patrol.py"),
        "--paper-ids",
        paper_ids,
        "--mode",
        mode,
        "--compact",
    ]
    print(">>", " ".join(cmd))
    completed = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    return completed.returncode


def print_instructions() -> None:
    print()
    print("=" * 60)
    print("ScholarGraph 浏览器全链路演示")
    print("=" * 60)
    print()
    print("终端 1（仓库根目录）— 启动后端（Demo Profile 必开）：")
    print("  # Linux/macOS")
    print("  export APP_PROFILE=demo")
    print("  uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000")
    print("  # Windows PowerShell")
    print("  $env:APP_PROFILE='demo'")
    print("  uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000")
    print("  # 说明：APP_PROFILE=demo 会自动叠加加载 .env.demo（RERANKER_ENABLED=true）")
    print()
    print("终端 2（frontend/）— 启动前端：")
    print("  cd frontend && npm install && npm run dev")
    print()
    print("演示 URL（按 progress.md §6 路径顺序）：")
    for label, url in DEMO_URLS:
        print(f"  - {label}: {url}")
    print()
    print("巡检页操作：")
    print("  1. 打开 /patrol")
    print("  2. paper_ids 输入 hss-001,hss-002")
    print("  3. mode 选择 lens_clash / contradiction / method_overlap / claim_evolution")
    print("  4. V2 模式使用 stem-001,stem-002（默认 seed 已包含 STEM 语料）")
    print("  5. 点击「运行巡检」，查看 insights、structured_points 与 node_refs 表格")
    print()
    print(f"后端 OpenAPI: {BACKEND_BASE}/docs")
    print("完整文档: docs/v1/eval/frontend-demo-path.md")
    print()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.skip_seed:
        exit_code = run_seed(include_stem=not args.no_stem_seed)
        if exit_code != 0:
            print(f"seed 失败，退出码 {exit_code}", file=sys.stderr)
            return exit_code

    if args.smoke_all_patrol:
        for mode in ("lens_clash", "contradiction", "method_overlap", "claim_evolution"):
            exit_code = run_patrol_smoke(mode)
            if exit_code != 0:
                print(f"patrol CLI 冒烟失败（{mode}），退出码 {exit_code}", file=sys.stderr)
                return exit_code
    elif args.smoke_patrol:
        exit_code = run_patrol_smoke(args.mode)
        if exit_code != 0:
            print(f"patrol CLI 冒烟失败，退出码 {exit_code}", file=sys.stderr)
            return exit_code

    print_instructions()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
