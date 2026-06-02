"""BE-2 agent tests exercise heuristic classify/extract, not mock_agents."""

from __future__ import annotations

import pytest
from backend.config import get_settings


@pytest.fixture(autouse=True)
def be2_heuristic_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    get_settings.cache_clear()
