"""Process Release Gate matrix — PROCESSING self-heal closed loop.

| 测试分类 | 测试用例命名 | 检验的防御边界 |
| --- | --- | --- |
| 逻辑/内存双检 | ``test_watchdog_slow_but_alive_extends_lease`` | 慢任务续租，不误杀 |
| 逻辑/内存双检 | ``test_watchdog_true_zombie_triggers_failed`` | 真僵尸 → PROCESS_TIMEOUT |
| 级联处决 | ``test_watchdog_kill_execution_order`` | abort ≺ SQL + 锁回流 |
| 世代熔断 | ``test_obsolete_run_id_write_blocked`` | Run_A 迟到写盘被弹回 |
| 隔离监控 | ``test_processing_watchdog_survives_loop_starvation`` | 主 loop 假死仍 sync 自愈 |
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
        "逻辑/内存双检",
        "test_watchdog_slow_but_alive_extends_lease",
        "tests/pipeline/test_processing_watchdog.py",
    ),
    (
        "逻辑/内存双检",
        "test_watchdog_true_zombie_triggers_failed",
        "tests/pipeline/test_processing_watchdog.py",
    ),
    (
        "级联处决",
        "test_watchdog_kill_execution_order",
        "tests/pipeline/test_processing_watchdog.py",
    ),
    (
        "世代熔断",
        "test_obsolete_run_id_write_blocked",
        "tests/pipeline/test_pipeline_generation_guard.py",
    ),
    (
        "隔离监控",
        "test_processing_watchdog_survives_loop_starvation",
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
