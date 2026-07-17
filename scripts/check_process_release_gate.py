#!/usr/bin/env python3
# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Process Release Gate — PROCESSING 全链路自愈矩阵（CI 硬阻断）。

五层核心场景（详见 ``tests/pipeline/test_process_release_gate_matrix.py``）：
弹性续租 / 硬杀清洗 / 资源扫尾 / 分布式熔断 / 物理解耦。

确保墙钟 + 冷启动 grace + 级联处决 + 世代熔断 + 主 loop 假死回归保持在
``@pytest.mark.process_release_gate`` 下可发现且通过。

Usage (repo root)::

    uv run python scripts/check_process_release_gate.py
    make process-release-gate
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TEST_NAMES: tuple[str, ...] = (
    "test_watchdog_slow_but_alive_extends_lease",
    "test_watchdog_true_zombie_triggers_failed",
    "test_watchdog_kill_execution_order",
    "test_watchdog_kill_lock_reflux_allows_bystander_reextract",
    "test_obsolete_run_id_write_blocked",
    "test_processing_watchdog_survives_loop_starvation",
    "test_cold_boot_spares_fresh_pending_within_grace",
    "test_wall_clock_fails_stale_pending_as_queue_timeout",
    "test_process_release_gate_matrix_catalog_is_complete",
)

_COLLECT_ROOTS = ("tests/pipeline",)


def _collect_nodeids() -> list[str]:
    nodeids: list[str] = []
    for collect_root in _COLLECT_ROOTS:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                collect_root,
                "--collect-only",
                "-q",
                "-m",
                "process_release_gate",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode not in {0, 5}:
            sys.stderr.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            raise SystemExit(
                f"pytest --collect-only -m process_release_gate failed in {collect_root} ({proc.returncode})"
            )
        nodeids.extend(line.strip() for line in proc.stdout.splitlines() if "::" in line)
    return nodeids


def _assert_required_present(nodeids: list[str]) -> list[str]:
    joined = "\n".join(nodeids)
    missing: list[str] = []
    for name in REQUIRED_TEST_NAMES:
        if not re.search(rf"::{name}$", joined, flags=re.MULTILINE):
            if not any(nodeid.endswith(f"::{name}") for nodeid in nodeids):
                missing.append(name)
    return missing


def main() -> int:
    print("==> process release-gate collect")
    nodeids = _collect_nodeids()
    print(f"collected {len(nodeids)} process_release_gate test(s)")
    for nodeid in nodeids:
        print(f"  - {nodeid}")

    missing = _assert_required_present(nodeids)
    if missing:
        print("MISSING required process release-gate tests:", file=sys.stderr)
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
        return 1

    print("==> process release-gate run")
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *_COLLECT_ROOTS,
            "-q",
            "--tb=short",
            "-m",
            "process_release_gate",
        ],
        cwd=REPO_ROOT,
        check=False,
    )
    if run.returncode != 0:
        print("FAILED: process_release_gate pytest", file=sys.stderr)
        return run.returncode
    print("process release-gate OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
