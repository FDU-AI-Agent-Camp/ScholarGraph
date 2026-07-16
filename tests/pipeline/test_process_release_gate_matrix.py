"""Process Release Gate — 全链路自动化验证矩阵一览.

CI 阻断：``make process-release-gate`` / ``make ci`` / ``make ci-patrol-release`` 首步
（``scripts/check_process_release_gate.py``，``@pytest.mark.process_release_gate``）。

## 核心五层（PROCESSING 自愈闭环）

| 测试场景分类 | 注入的边界条件 | 期望的自愈与防卫动作 | 核心断言指标 (CI 阻断点) | 用例 |
| --- | --- | --- | --- | --- |
| 弹性续租验证 | 纸面超时 + 内存 Task 为 running | 判定为慢任务，延长租约 | 状态保持 PROCESSING，且 ``updated_at`` 成功向前 Bump | ``test_watchdog_slow_but_alive_extends_lease`` |
| 硬杀清洗验证 | 纸面超时 + 内存 Task 已断娘 | 判定为真僵尸，启动强拆 | 状态变更为 FAILED，且 ``error_code`` / 消息面含 ``PROCESS_TIMEOUT`` | ``test_watchdog_true_zombie_triggers_failed`` |
| 资源扫尾验证 | 僵尸任务正霸占 ``asyncio.Lock``（及遗弃 wipe claim） | 处决算子前置，强制收回锁 | 旁路排队协程秒级通关，无二次死锁；abort ≺ FAILED commit | ``test_watchdog_kill_execution_order`` + ``test_watchdog_kill_lock_reflux_allows_bystander_reextract`` |
| 分布式熔断验证 | Run_A 被宣判死亡，新跑 Run_B；Run_A 迟到回写 | 令牌校验防线启动，悲观拒绝 | 强抛 ``ObsoletePipelineGenerationError``，GraphStore/终端 SQL 拒绝脏写，Run_B 元数据未污染 | ``test_obsolete_run_id_write_blocked`` |
| 物理解耦演练 | 主事件循环遭遇 5s 硬饥饿 | 独立扫描线程免死，照常 Commit | 假死期间 DB 侧自愈完成，看门狗独立生存率 100% | ``test_processing_watchdog_survives_loop_starvation`` |

## 附录（同门禁，防 PENDING / 冷启动退化）

| 测试分类 | 用例 | 检验的防御边界 |
| --- | --- | --- |
| 冷启动防误伤 | ``test_cold_boot_spares_fresh_pending_within_grace`` | boot−ε 放过极新 pending |
| 双阈值归因 | ``test_wall_clock_fails_stale_pending_as_queue_timeout`` | pending → QUEUE_TIMEOUT |

Canonical bodies carry ``@pytest.mark.process_release_gate``.
This module asserts the catalog stays wired.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# (场景分类, 测试名, 相对路径) — 顺序与上表核心五层 + 附录一致。
PROCESS_RELEASE_GATE_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "弹性续租验证",
        "test_watchdog_slow_but_alive_extends_lease",
        "tests/pipeline/test_processing_watchdog.py",
    ),
    (
        "硬杀清洗验证",
        "test_watchdog_true_zombie_triggers_failed",
        "tests/pipeline/test_processing_watchdog.py",
    ),
    (
        "资源扫尾验证",
        "test_watchdog_kill_execution_order",
        "tests/pipeline/test_processing_watchdog.py",
    ),
    (
        "资源扫尾验证",
        "test_watchdog_kill_lock_reflux_allows_bystander_reextract",
        "tests/pipeline/test_processing_watchdog.py",
    ),
    (
        "分布式熔断验证",
        "test_obsolete_run_id_write_blocked",
        "tests/pipeline/test_pipeline_generation_guard.py",
    ),
    (
        "物理解耦演练",
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

# 核心五层场景名（附录除外）— 供目录完整性与文档交叉引用。
PROCESS_RELEASE_GATE_CORE_SCENARIOS: tuple[str, ...] = (
    "弹性续租验证",
    "硬杀清洗验证",
    "资源扫尾验证",
    "分布式熔断验证",
    "物理解耦演练",
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

    catalog_categories = {category for category, _, _ in PROCESS_RELEASE_GATE_CASES}
    for scenario in PROCESS_RELEASE_GATE_CORE_SCENARIOS:
        assert scenario in catalog_categories, f"core scenario missing from catalog: {scenario}"
