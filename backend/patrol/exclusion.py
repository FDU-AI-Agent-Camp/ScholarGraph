# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Structured exclusion / negative-determination contracts for channel-B Patrol insights.

When analyzers finish but cannot produce a ready insight, they return HTTP 200 with
``status=insufficient_data`` plus ``exclusion_logic`` explaining why (P11 / F7).
This is a conclusive business outcome, not an error — contrast channel A (HTTP 422).
"""

from __future__ import annotations

from typing import Any

from backend.schemas.patrol import PatrolExclusionLogic, PatrolExclusionReason

# Stable phase tags for exclusion_logic.phase (machine-readable pipeline stage).
PHASE_PARADIGM_GATE = "PARADIGM_GATE"
PHASE_NODE_PRECHECK = "NODE_PRECHECK"
PHASE_OVERLAP_MATCH = "OVERLAP_MATCH"
PHASE_RQ_ALIGNMENT = "RQ_ALIGNMENT"
PHASE_CLAIM_RECALL = "CLAIM_RECALL"


def make_exclusion_logic(
    reason_code: PatrolExclusionReason,
    *,
    phase: str,
    description: str,
    metrics: dict[str, Any] | None = None,
) -> PatrolExclusionLogic:
    """Build a typed exclusion payload for an insufficient_data insight."""
    return PatrolExclusionLogic(
        phase=phase,
        reason_code=reason_code,
        description=description,
        metrics=dict(metrics or {}),
    )
