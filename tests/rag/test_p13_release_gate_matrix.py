"""P13 Release Gate matrix — catalog of debt-regression defenses.

| 测试分类 | 测试用例命名 | 检验的防御边界 |
| --- | --- | --- |
| 并发/时域 | ``test_orphan_thread_cannot_override_new_generation`` | Run ID 世代双检拦截率 |
| 自愈/补偿 | ``test_cleanup_task_removes_delayed_orphan_data`` | Chroma 后置补偿扫尾 |
| 隔离监控 | ``test_watchdog_works_during_event_loop_starvation`` | Watchdog 物理线程隔离 |
| 临界自愈 | ``test_cold_boot_reconciliation_clears_zombie_states`` | 冷启动僵尸清洗 |

Canonical bodies live in sibling modules and carry ``@pytest.mark.p13_release_gate``.
This module only asserts the catalog stays wired (prevents silent rename/delete regressions).
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

P13_RELEASE_GATE_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "并发/时域",
        "test_orphan_thread_cannot_override_new_generation",
        "tests/rag/test_orphan_run_race_amplification.py",
    ),
    (
        "自愈/补偿",
        "test_cleanup_task_removes_delayed_orphan_data",
        "tests/rag/test_orphan_run_race_amplification.py",
    ),
    (
        "隔离监控",
        "test_watchdog_works_during_event_loop_starvation",
        "tests/rag/test_watchdog_main_loop_starvation.py",
    ),
    (
        "临界自愈",
        "test_cold_boot_reconciliation_clears_zombie_states",
        "tests/rag/test_indexing_watchdog.py",
    ),
)


@pytest.mark.p13_release_gate
def test_p13_release_gate_matrix_catalog_is_complete() -> None:
    """Static catalog: each release-gate nodeid must still exist as a ``def`` in-tree."""
    missing: list[str] = []
    for _category, test_name, rel_path in P13_RELEASE_GATE_CASES:
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
        # Require the mark on the decorator block immediately above the def.
        window = text[max(0, pos - 180) : pos]
        if "@pytest.mark.p13_release_gate" not in window:
            missing.append(f"{test_name} missing @pytest.mark.p13_release_gate above def")
    assert missing == [], "P13 release-gate matrix regressions:\n" + "\n".join(missing)
