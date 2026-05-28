"""Unit tests: conditional routing between pipeline steps."""

import pytest
from backend.graph.state import WorkflowState
from backend.graph.workflow import _route_after_step


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ({"failed": False}, "continue"),
        ({}, "continue"),
        ({"failed": True}, "fail"),
        ({"failed": True, "error_code": "INGEST_FAILED"}, "fail"),
    ],
)
def test_route_after_step(state: WorkflowState, expected: str) -> None:
    assert _route_after_step(state) == expected
