# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Golden config snapshot validation for Patrol live regression baselines."""

from __future__ import annotations

from backend.config import Settings, get_settings
from tests.fixtures.patrol_method_overlap_golden import (
    GoldenConfigSnapshot,
    MethodOverlapGoldenSet,
    load_method_overlap_golden_set,
)

_BASELINE_UPDATE_HINT = (
    "若阈值或 Embedding 模型变更有意为之，请同步更新 "
    "data/patrol_method_overlap_golden.json 的 config_snapshot，并重新跑 "
    "pytest -m live_patrol_logic 与 scripts/benchmark_patrol.py --mode all --live 以刷新基准线。"
)


class GoldenConfigSnapshotMismatch(Exception):
    """Raised when runtime Settings diverge from the golden config snapshot."""

    def __init__(self, mismatches: list[str]) -> None:
        self.mismatches = mismatches
        detail = "\n".join(f"  - {line}" for line in mismatches)
        message = (
            f"Patrol golden config_snapshot 与当前运行环境不一致，已阻断 live 回归。\n{detail}\n{_BASELINE_UPDATE_HINT}"
        )
        super().__init__(message)


def resolve_runtime_config_snapshot(settings: Settings) -> GoldenConfigSnapshot:
    """Build the config tuple that live regression expects to match."""
    return GoldenConfigSnapshot(
        patrol_semantic_threshold=settings.patrol_semantic_threshold,
        embedding_model=settings.embedding_model.strip(),
        enable_patrol_semantic_path=settings.enable_patrol_semantic_path,
    )


def collect_config_snapshot_mismatches(
    snapshot: GoldenConfigSnapshot,
    settings: Settings,
) -> list[str]:
    """Return human-readable mismatch lines (empty when aligned)."""
    runtime = resolve_runtime_config_snapshot(settings)
    mismatches: list[str] = []

    if snapshot.patrol_semantic_threshold != runtime.patrol_semantic_threshold:
        mismatches.append(
            "PATROL_SEMANTIC_THRESHOLD: "
            f"golden={snapshot.patrol_semantic_threshold} runtime={runtime.patrol_semantic_threshold}"
        )
    if snapshot.embedding_model.strip() != runtime.embedding_model:
        mismatches.append(f"EMBEDDING_MODEL: golden={snapshot.embedding_model!r} runtime={runtime.embedding_model!r}")
    if snapshot.enable_patrol_semantic_path != runtime.enable_patrol_semantic_path:
        mismatches.append(
            "ENABLE_PATROL_SEMANTIC_PATH: "
            f"golden={snapshot.enable_patrol_semantic_path} runtime={runtime.enable_patrol_semantic_path}"
        )
    return mismatches


def validate_golden_config_snapshot(
    *,
    settings: Settings | None = None,
    golden: MethodOverlapGoldenSet | None = None,
) -> GoldenConfigSnapshot:
    """Assert runtime Settings match the golden header snapshot."""
    resolved_golden = golden or load_method_overlap_golden_set()
    resolved_settings = settings or get_settings()
    mismatches = collect_config_snapshot_mismatches(resolved_golden.config_snapshot, resolved_settings)
    if mismatches:
        raise GoldenConfigSnapshotMismatch(mismatches)
    return resolved_golden.config_snapshot


def format_config_snapshot_report(
    *,
    settings: Settings | None = None,
    golden: MethodOverlapGoldenSet | None = None,
) -> dict[str, object]:
    """Return a JSON-serializable alignment report for CLI / CI logs."""
    resolved_golden = golden or load_method_overlap_golden_set()
    resolved_settings = settings or get_settings()
    runtime = resolve_runtime_config_snapshot(resolved_settings)
    mismatches = collect_config_snapshot_mismatches(resolved_golden.config_snapshot, resolved_settings)
    return {
        "aligned": not mismatches,
        "golden_snapshot": resolved_golden.config_snapshot.model_dump(),
        "runtime_snapshot": runtime.model_dump(),
        "mismatches": mismatches,
        "baseline_update_hint": _BASELINE_UPDATE_HINT,
    }
