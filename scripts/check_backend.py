#!/usr/bin/env python3
"""
后端静态检查与测试门禁（ruff + pytest）。

在仓库根目录执行::

    uv run python scripts/check_backend.py
    uv run python scripts/check_backend.py --lint-only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence

RUFF_TARGETS = ("backend", "tests", "scripts")
DEFAULT_PYTEST_MARKER = "not red and not live_mineru and not live_grobid and not live_benchmark"
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
    parser = argparse.ArgumentParser(description="Backend lint, format, and pytest gate.")
    parser.add_argument(
        "--lint-only",
        action="store_true",
        help="Run ruff only (skip pytest).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    steps: list[tuple[str, list[str]]] = [
        ("ruff check", ["ruff", "check", *RUFF_TARGETS]),
        ("ruff format --check", ["ruff", "format", "--check", *RUFF_TARGETS]),
    ]
    if not args.lint_only:
        # Use ``python -m pytest`` to avoid Windows entry-point canonicalisation issues.
        steps.append(("pytest", [sys.executable, "-m", "pytest", "-q", "-m", DEFAULT_PYTEST_MARKER]))

    for label, command in steps:
        if run_step(label, command) != EXIT_SUCCESS:
            return EXIT_FAILURE
    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
