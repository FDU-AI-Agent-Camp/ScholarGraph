#!/usr/bin/env python
"""Validate Patrol golden config snapshots against runtime Settings.

Used by Nightly/Release gate before ``pytest -m live_patrol_logic`` and
``scripts/benchmark_patrol.py --mode all --live``.

Usage (from repo root)::

    uv run python scripts/validate_patrol_golden.py
    uv run python scripts/validate_patrol_golden.py --strict
    uv run python scripts/validate_patrol_golden.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.fixtures.patrol_golden_config_snapshot import format_config_snapshot_report  # noqa: E402

_EXIT_OK = 0
_EXIT_MISMATCH = 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Patrol 金标 config_snapshot 对齐校验")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="配置不一致时以非零退出码阻断（Release/Nightly gate 使用）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 报告",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = format_config_snapshot_report()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report["aligned"]:
        print("[OK] Patrol golden config_snapshot 与运行环境一致")
    else:
        print("[FAIL] Patrol golden config_snapshot 与运行环境不一致")
        for line in report["mismatches"]:
            print(f"  - {line}")
        print(report["baseline_update_hint"])

    if report["aligned"]:
        return _EXIT_OK
    return _EXIT_MISMATCH if args.strict else _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
