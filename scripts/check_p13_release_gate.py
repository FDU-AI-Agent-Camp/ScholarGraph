#!/usr/bin/env python3
# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""P13 Release Gate — collect + run the orphan-thread / watchdog debt matrix.

Ensures the four canonical regression cases (plus catalog meta-test) remain
discoverable under ``@pytest.mark.p13_release_gate`` and pass.

Usage (repo root)::

    uv run python scripts/check_p13_release_gate.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TEST_NAMES: tuple[str, ...] = (
    "test_orphan_thread_cannot_override_new_generation",
    "test_cleanup_task_removes_delayed_orphan_data",
    "test_watchdog_works_during_event_loop_starvation",
    "test_cold_boot_reconciliation_clears_zombie_states",
    "test_p13_release_gate_matrix_catalog_is_complete",
)


# Scope to tests/rag so unrelated modules (e.g. patrol suite gates that load
# golden JSON at collection time) cannot abort P13 collect with Import/FileNotFound.
_P13_COLLECT_ROOT = "tests/rag"


def _collect_p13_nodeids() -> list[str]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            _P13_COLLECT_ROOT,
            "--collect-only",
            "-q",
            "-m",
            "p13_release_gate",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode not in {0, 5}:  # 5 = no tests collected
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"pytest --collect-only -m p13_release_gate failed ({proc.returncode})")
    # Lines look like: tests/rag/foo.py::test_bar
    return [line.strip() for line in proc.stdout.splitlines() if "::" in line]


def _assert_required_present(nodeids: list[str]) -> list[str]:
    joined = "\n".join(nodeids)
    missing: list[str] = []
    for name in REQUIRED_TEST_NAMES:
        if not re.search(rf"::{name}$", joined, flags=re.MULTILINE):
            # Windows / pytest may print with package prefix; also match trailing.
            if not any(nodeid.endswith(f"::{name}") for nodeid in nodeids):
                missing.append(name)
    return missing


def main() -> int:
    print("==> P13 release-gate collect")
    nodeids = _collect_p13_nodeids()
    print(f"collected {len(nodeids)} p13_release_gate test(s)")
    for nodeid in nodeids:
        print(f"  - {nodeid}")

    missing = _assert_required_present(nodeids)
    if missing:
        print("MISSING required P13 release-gate tests:", file=sys.stderr)
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
        return 1

    print("==> P13 release-gate run")
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            _P13_COLLECT_ROOT,
            "-q",
            "--tb=short",
            "-m",
            "p13_release_gate",
        ],
        cwd=REPO_ROOT,
        check=False,
    )
    if run.returncode != 0:
        print("FAILED: p13_release_gate pytest", file=sys.stderr)
        return run.returncode
    print("P13 release-gate OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
