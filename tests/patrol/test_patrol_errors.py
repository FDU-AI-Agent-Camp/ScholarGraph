# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""PatrolError unit tests."""

from backend.patrol.errors import PatrolError


def test_patrol_error_carries_code_message_and_status() -> None:
    exc = PatrolError("GRAPH_NOT_READY", "图谱未就绪", status_code=409)
    assert exc.code == "GRAPH_NOT_READY"
    assert exc.message == "图谱未就绪"
    assert exc.status_code == 409
    assert str(exc) == "图谱未就绪"
