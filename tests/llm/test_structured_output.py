"""Tests for backend.llm.structured_output parsing helpers."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from backend.llm.structured_output import (
    _extract_json,
    _parse_model_response,
    _strip_markdown_fences,
)


class _SampleModel(BaseModel):
    name: str = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def _record_context_warning(cls, value: str, info: ValidationInfo) -> str:
        context = info.context
        if isinstance(context, dict):
            warnings = context.get("warnings")
            if isinstance(warnings, list):
                warnings.append("name_validated")
        return value

    @model_validator(mode="after")
    def _merge_warnings(self, info: ValidationInfo) -> "_SampleModel":
        context = info.context
        if isinstance(context, dict):
            warnings = context.get("warnings")
            if isinstance(warnings, list):
                self.warnings = list(dict.fromkeys(self.warnings + warnings))
        return self


class TestStripMarkdownFences:
    def test_strips_json_fence(self) -> None:
        raw = '```json\n{"name": "alice"}\n```'
        assert _strip_markdown_fences(raw) == '{"name": "alice"}'

    def test_strips_plain_fence(self) -> None:
        raw = '```\n{"name": "alice"}\n```'
        assert _strip_markdown_fences(raw) == '{"name": "alice"}'

    def test_returns_clean_json_unchanged(self) -> None:
        raw = '{"name": "alice"}'
        assert _strip_markdown_fences(raw) == raw


class TestExtractJson:
    def test_extracts_object_from_explanatory_text(self) -> None:
        raw = 'Here is the result: {"name": "alice"} Thanks!'
        assert _extract_json(raw) == '{"name": "alice"}'

    def test_extracts_array_from_explanatory_text(self) -> None:
        raw = 'Items: [{"name": "alice"}, {"name": "bob"}] Done.'
        assert _extract_json(raw) == '[{"name": "alice"}, {"name": "bob"}]'

    def test_handles_nested_braces(self) -> None:
        raw = '```json\n{"payload": {"nested": "value"}}\n```'
        assert _extract_json(raw) == '{"payload": {"nested": "value"}}'


class TestParseModelResponse:
    def test_parses_plain_json(self) -> None:
        result = _parse_model_response('{"name": "alice"}', _SampleModel)
        assert result.name == "alice"

    def test_parses_fenced_json(self) -> None:
        raw = '```json\n{"name": "bob"}\n```'
        result = _parse_model_response(raw, _SampleModel)
        assert result.name == "bob"

    def test_propagates_context_warnings(self) -> None:
        raw = '{"name": "carol"}'
        result = _parse_model_response(raw, _SampleModel, context={"warnings": []})
        assert "name_validated" in result.warnings

    def test_raises_for_non_json_content(self) -> None:
        with pytest.raises(ValueError):  # noqa: PT011
            _parse_model_response("No JSON here", _SampleModel)
