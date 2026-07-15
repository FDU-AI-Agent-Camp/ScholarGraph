"""Process Release Gate matrix — processing / pending wall-clock defenses.

| 测试分类 | 测试用例命名 | 检验的防御边界 |
| --- | --- | --- |
| 隔离监控 | ``test_processing_watchdog_loop_starvation`` | processing Watchdog 物理线程隔离 |
| 冷启动防误伤 | ``test_cold_boot_spares_fresh_pending_within_grace`` | boot−ε 放过极新 pending |
| 双阈值归因 | ``test_wall_clock_fails_stale_pending_as_queue_timeout`` | pending → QUEUE_TIMEOUT |

Canonical bodies carry ``@pytest.mark.process_release_gate``.
This module asserts the catalog stays wired.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

PROCESS_RELEASE_GATE_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "隔离监控",
        "test_processing_watchdog_loop_starvation",
        "tests/pipeline/test_processing_watchdog_loop_starvation.py",
    ),
    (
        "冷启动防误伤",
        "test_cold_boot_spares_fresh_pending_within_grace",
        "tests/pipeline/test_processing_watchdog.py",
    ),
    (
        "双阈值归因",
        "test_wall_clock_fails_stale_pending_as_queue_timeout",
        "tests/pipeline/test_processing_watchdog.py",
    ),
)


@pytest.mark.process_release_gate
def test_process_release_gate_matrix_catalog_is_complete() -> None:
    missing: list[str] = []
    for _category, test_name, rel_path in PROCESS_RELEASE_GATE_CASES:
        path = REPO_ROOT / rel_path
        if not path.is_file():
            missing.append(f"{test_name} (missing file {rel_path})")
            continue
        text = path.read_text(encoding="utf-8")
        needle = f"def {test_name}("
        pos = text.find(needle)
        if pos < 0:
            missing.append(f"{test_name} (not defined in {rel_path})")
            continue
        window = text[max(0, pos - 220) : pos]
        if "@pytest.mark.process_release_gate" not in window:
            missing.append(f"{test_name} missing @pytest.mark.process_release_gate above def")
    assert missing == [], "process release-gate matrix regressions:\n" + "\n".join(missing)
