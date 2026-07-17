# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""JSON Schema fragment for PatrolInsight.degradation_profile (P9 contract)."""

from __future__ import annotations

from typing import Any

# Draft-2020-12 compatible fragment used by fault-injection contract tests.
PATROL_DEGRADATION_PROFILE_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "component",
        "reason_code",
        "affected_papers",
        "severity",
        "timestamp",
    ],
    "properties": {
        "component": {"type": "string", "const": "RAG_CONTEXT"},
        "reason_code": {
            "type": "string",
            "enum": ["INDEX_NOT_READY", "QUERY_FAILED", "VECTOR_STORE_UNAVAILABLE"],
        },
        "affected_papers": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
        },
        "severity": {"type": "string", "enum": ["WARNING", "ERROR"]},
        "timestamp": {"type": "string", "minLength": 1},
    },
}


def assert_degradation_profile_contract(payload: object) -> None:
    """Strict contract check: profile must be a complete object (never null)."""
    assert payload is not None, "degradation_profile must not be null when degraded"
    assert isinstance(payload, dict), "degradation_profile must be an object"

    try:
        import jsonschema
    except ImportError:  # pragma: no cover — pydantic fallback when jsonschema absent
        from backend.schemas.patrol import PatrolDegradationProfile

        PatrolDegradationProfile.model_validate(payload)
        return

    jsonschema.validate(instance=payload, schema=PATROL_DEGRADATION_PROFILE_JSON_SCHEMA)
