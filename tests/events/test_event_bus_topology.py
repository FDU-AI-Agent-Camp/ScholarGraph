"""P10: EventBus topology — exclusive official RAG handler, no temporary_* subscribers."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from backend.events.bus import get_event_bus, reset_event_bus_cache
from backend.events.types import EventType
from backend.rag.handlers import (
    RAG_PIPELINE_HANDLER_NAME,
    assert_exclusive_rag_pipeline_subscriber,
    on_pipeline_finalized_for_rag,
    register_rag_pipeline_finalized_handler,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"


def test_event_bus_topology_single_official_rag_handler() -> None:
    reset_event_bus_cache()
    bus = get_event_bus()
    handlers = list(bus._handlers.get(EventType.PIPELINE_FINALIZED, []))
    assert len(handlers) == 1
    assert handlers[0] is on_pipeline_finalized_for_rag
    assert handlers[0].__name__ == RAG_PIPELINE_HANDLER_NAME
    assert_exclusive_rag_pipeline_subscriber()


def test_exclusive_guard_rejects_second_rag_named_subscriber() -> None:
    reset_event_bus_cache()
    bus = get_event_bus()

    async def rogue_rag_index_handler(_event: object) -> None:
        return None

    bus.subscribe(EventType.PIPELINE_FINALIZED, rogue_rag_index_handler)
    with pytest.raises(RuntimeError, match="Exclusive RAG subscription violated"):
        assert_exclusive_rag_pipeline_subscriber()
    bus._handlers[EventType.PIPELINE_FINALIZED].remove(rogue_rag_index_handler)
    assert_exclusive_rag_pipeline_subscriber()
    register_rag_pipeline_finalized_handler(force=True)


def test_no_temporary_pipeline_subscriber_symbols_in_backend() -> None:
    violations: list[str] = []
    forbidden_prefixes = ("temporary_", "temp_pipeline_")
    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(node.name.startswith(prefix) for prefix in forbidden_prefixes):
                    rel = path.relative_to(BACKEND_ROOT).as_posix()
                    violations.append(f"{rel}:{node.name}")
    assert violations == [], "banned temporary_* subscribers found:\n" + "\n".join(violations)


def test_pipeline_finalized_handlers_module_has_no_temporary_symbol() -> None:
    source = (BACKEND_ROOT / "events" / "pipeline_finalized_handlers.py").read_text(encoding="utf-8")
    assert "temporary_pipeline_finalized_rag_handler" not in source
    assert "def temporary_" not in source
