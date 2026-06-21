"""Tests for structured output parsing and JSON repair (Slice 2 robustness)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.llm.structured_output import _parse_model_response, ainvoke_structured
from backend.schemas.extract_phase import ExtractedNodeList
from backend.schemas.paradigm import Paradigm


def _node_schema() -> type[ExtractedNodeList]:
    return ExtractedNodeList


class TestParseModelResponse:
    def test_valid_json_parses(self) -> None:
        raw = '{"paradigm": "HSS", "nodes": [{"id": "n1", "label": "L", "type": "Thesis"}]}'
        result = _parse_model_response(raw, ExtractedNodeList)
        assert len(result.nodes) == 1
        assert result.nodes[0].id == "n1"

    def test_markdown_fences_are_stripped(self) -> None:
        raw = '```json\n{"paradigm": "HSS", "nodes": [{"id": "n1", "label": "L", "type": "Thesis"}]}\n```'
        result = _parse_model_response(raw, ExtractedNodeList)
        assert len(result.nodes) == 1

    def test_truncated_json_is_repaired(self) -> None:
        raw = '{"paradigm": "HSS", "nodes": [{"id": "n1", "label": "L", "type": "Thesis"}'
        result = _parse_model_response(raw, ExtractedNodeList)
        assert len(result.nodes) == 1
        assert result.nodes[0].id == "n1"

    def test_unrepairable_json_raises(self) -> None:
        raw = "this is not json at all"
        with pytest.raises(ValueError, match="non-JSON"):
            _parse_model_response(raw, ExtractedNodeList)


class TestAinvokeStructured:
    async def test_parses_response(self) -> None:
        client = MagicMock()
        client.fallback_chat = None
        client.chat.ainvoke = AsyncMock(
            return_value=MagicMock(
                content='{"paradigm": "HSS", "nodes": [{"id": "n1", "label": "L", "type": "Thesis"}]}'
            )
        )

        result = await ainvoke_structured(
            client,
            ExtractedNodeList,
            [MagicMock()],
        )
        assert result.paradigm == Paradigm.HSS
        assert len(result.nodes) == 1

    async def test_repair_avoids_extra_llm_calls(self) -> None:
        client = MagicMock()
        client.fallback_chat = None
        client.chat.ainvoke = AsyncMock(
            return_value=MagicMock(content='{"paradigm": "HSS", "nodes": [{"id": "n1", "label": "L", "type": "Thesis"}')
        )

        result = await ainvoke_structured(
            client,
            ExtractedNodeList,
            [MagicMock()],
        )
        assert len(result.nodes) == 1
        client.chat.ainvoke.assert_awaited_once()
