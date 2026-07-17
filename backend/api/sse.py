# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""SSE wire-format helpers (V1 api-contract.md §8)."""

from __future__ import annotations

import json

QA_STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def format_sse_event(event: str, data: dict) -> str:
    """Format one SSE frame: ``event: …\\ndata: …\\n\\n``."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
