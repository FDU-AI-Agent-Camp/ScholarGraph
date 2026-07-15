"""Force-wipe lifecycle matrix — claim ∪ read isolation ∪ two-wave sweep.

| 场景维度 | 测例 | 防御边界 |
| --- | --- | --- |
| Claim 拦截 | ``test_foreign_worker_claim_blocks_reextract`` | 跨 worker 409 |
| Claim 拦截 | ``test_delete_and_reextract_share_cluster_mutex`` | delete∪reextract 互斥 |
| Claim 拦截 | ``test_cluster_advisory_lock`` | 双 worker force-DELETE 1 胜 1×409 |
| 读时失明 | ``test_query_fail_closed_when_active_run_missing`` | 无 active → 空结果 |
| 读时失明 | ``test_ghost_vector_logical_isolation`` | HybridRetriever 不见 Run_A |
| Wave2 | ``test_wipe_wave2_delete_run_after_short_delay`` | 延迟 ``delete_run`` |
| Wave2 | ``test_force_delete_schedules_wave2_after_wave1`` | wipe 接线 |
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

WIPE_LIFECYCLE_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "并发 Claim 拦截",
        "test_foreign_worker_claim_blocks_reextract",
        "tests/concurrency/test_friction_race_and_generation.py",
    ),
    (
        "并发 Claim 拦截",
        "test_delete_and_reextract_share_cluster_mutex",
        "tests/concurrency/test_friction_race_and_generation.py",
    ),
    (
        "并发 Claim 拦截",
        "test_cluster_advisory_lock",
        "tests/rag/test_wipe_boundary_friction.py",
    ),
    (
        "迟到写入 / 读时失明",
        "test_query_fail_closed_when_active_run_missing",
        "tests/rag/test_wipe_vector_sweep.py",
    ),
    (
        "迟到写入 / 读时失明",
        "test_ghost_vector_logical_isolation",
        "tests/rag/test_wipe_boundary_friction.py",
    ),
    (
        "存储扫墓 Wave2",
        "test_wipe_wave2_delete_run_after_short_delay",
        "tests/rag/test_wipe_vector_sweep.py",
    ),
    (
        "存储扫墓 Wave2",
        "test_force_delete_schedules_wave2_after_wave1",
        "tests/rag/test_wipe_vector_sweep.py",
    ),
)


@pytest.mark.asyncio
async def test_wipe_lifecycle_matrix_catalog_is_complete() -> None:
    """Catalog wiring: every blueprint row points at an on-disk test definition."""
    for _dimension, test_name, rel_path in WIPE_LIFECYCLE_CASES:
        path = REPO_ROOT / rel_path
        assert path.is_file(), f"missing matrix file: {rel_path}"
        source = path.read_text(encoding="utf-8")
        assert f"def {test_name}" in source or f"async def {test_name}" in source, (
            f"{test_name} not found in {rel_path}"
        )
