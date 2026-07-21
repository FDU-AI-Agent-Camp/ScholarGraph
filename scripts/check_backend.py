#!/usr/bin/env python3
# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""
后端静态检查与测试门禁（ruff + pyright + pytest）。

此脚本面向本地开发，尤其是 Windows 环境（没有 make 时）。
线上 Ubuntu CI 使用 Makefile 的 ``make ci`` 目标一键执行。

在仓库根目录执行::

    uv run python scripts/check_backend.py          # 仅检查，不修改文件
    uv run python scripts/check_backend.py --fix    # 自动修复并格式化
    uv run python scripts/check_backend.py --lint-only

执行顺序（前一步失败则停止）：
1. ruff check        （默认不自动修复）
2. ruff format --check
3. pyright backend   （静态类型检查）
4. RAG I/O timeout 静态审计 + PaperService LoD AST + P13 release-gate 矩阵
5. pytest            （动态单元测试）
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence

RUFF_TARGETS = ("backend", "tests", "scripts")
DEFAULT_PYTEST_MARKER = (
    "not red and not live_patrol_logic and not live_qa_logic and not demo_profile_check "
    "and not live_mineru and not live_grobid and not live_benchmark and not live_e10 "
    "and not live_judge and not live_head_merge"
)
EXIT_SUCCESS = 0
EXIT_FAILURE = 1


def run_step(label: str, command: Sequence[str]) -> int:
    print(f"\n==> {label}")
    print(" ".join(command))
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        print(f"FAILED: {label}", file=sys.stderr)
    return result.returncode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backend lint, type check, and pytest gate.")
    parser.add_argument(
        "--lint-only",
        action="store_true",
        help="Run ruff and pyright only (skip pytest).",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix ruff issues and format files instead of just checking.",
    )
    parser.add_argument(
        "--no-fix",
        action="store_true",
        help="Deprecated: default behavior is already check-only.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.fix:
        ruff_check_cmd = ["ruff", "check", "--fix", *RUFF_TARGETS]
        ruff_format_cmd = ["ruff", "format", *RUFF_TARGETS]
    else:
        ruff_check_cmd = ["ruff", "check", *RUFF_TARGETS]
        ruff_format_cmd = ["ruff", "format", "--check", *RUFF_TARGETS]

    steps: list[tuple[str, list[str]]] = [
        ("ruff check", ruff_check_cmd),
        ("ruff format", ruff_format_cmd),
        ("pyright", [sys.executable, "-m", "pyright", "backend"]),
        # P13: keep wait_for / httpx timeout / [P13_WATCHDOG_HEAL] wire unbroken.
        ("rag io timeouts", [sys.executable, "scripts/check_rag_io_timeouts.py"]),
        # Architecture: forbid piercing PaperService._pipeline_repo outside the facade.
        ("pipeline repo lod", [sys.executable, "scripts/check_pipeline_repo_lod.py"]),
        # Architecture: forbid run_async / async_bridge inside backend/services (async SSOT).
        ("services no run_async", [sys.executable, "scripts/check_services_no_run_async.py"]),
        # Phase-3: embedded-bridge ban on services + patrol (whitelist: adapters/CLI/tests).
        ("no embedded bridge", [sys.executable, "scripts/check_no_embedded_bridge.py"]),
        # Phase-2: hot-path modules must await PaperService APIs (no run_async wrapper).
        ("async hotpath await", [sys.executable, "scripts/check_async_hotpath_await.py"]),
        # P13: orphan-thread + watchdog debt matrix (generation / compensate / starve / cold-boot).
        ("p13 release gate", [sys.executable, "scripts/check_p13_release_gate.py"]),
        # Parallel: processing/pending wall-clock + cold-boot grace matrix.
        ("process release gate", [sys.executable, "scripts/check_process_release_gate.py"]),
    ]
    if not args.lint_only:
        # Use ``python -m pytest`` to avoid Windows entry-point canonicalisation issues.
        steps.append(
            (
                "pytest",
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "--tb=short",
                    "-m",
                    DEFAULT_PYTEST_MARKER,
                ],
            )
        )

    for label, command in steps:
        if run_step(label, command) != EXIT_SUCCESS:
            return EXIT_FAILURE
    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
