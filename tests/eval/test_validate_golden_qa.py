"""Unit tests for scripts/validate_golden_qa.py helpers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from tests.conftest import REPO_ROOT

_VALIDATE_SCRIPT = REPO_ROOT / "scripts" / "validate_golden_qa.py"


@pytest.fixture
def validate_golden_qa_module():
    spec = importlib.util.spec_from_file_location("validate_golden_qa", _VALIDATE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_golden_qa"] = module
    spec.loader.exec_module(module)
    return module


def test_validate_chunk_id_format_accepts_canonical_ids(validate_golden_qa_module) -> None:
    mod = validate_golden_qa_module
    assert mod.validate_chunk_id_format("stem-001:chunk:42", expected_paper_id="stem-001") is None


def test_validate_chunk_id_format_rejects_legacy_underscore_ids(validate_golden_qa_module) -> None:
    mod = validate_golden_qa_module
    error = mod.validate_chunk_id_format("stem-001_chunk_42", expected_paper_id="stem-001")
    assert error is not None
    assert "legacy" in error


def test_mock_chunk_index_loads_stem_manifest(validate_golden_qa_module) -> None:
    mod = validate_golden_qa_module
    index = mod.MockChunkIndex.load_from_repo(REPO_ROOT / "data" / "chunk_manifests")
    assert index.has_chunk("stem-001", "stem-001:chunk:42") is True
    assert index.has_chunk("stem-001", "stem-001:chunk:99") is False


def test_mock_chunk_index_merges_mock_vector_store(validate_golden_qa_module) -> None:
    mod = validate_golden_qa_module
    index = mod.MockChunkIndex.load_from_repo(
        REPO_ROOT / "data" / "chunk_manifests",
        mock_vector_path=REPO_ROOT / "data" / "mock_vector_store.json",
    )
    assert index.has_chunk_with_text("stem-001", "stem-001:chunk:42") is True
    preview = index.chunk_text("stem-001", "stem-001:chunk:42")
    assert preview is not None
    assert "78.5%" in preview


def test_validate_numeric_pattern_token_accepts_percent_and_decimal(validate_golden_qa_module) -> None:
    mod = validate_golden_qa_module
    assert mod.validate_numeric_pattern_token("78.5%") is None
    assert mod.validate_numeric_pattern_token("0.001") is None
    assert mod.validate_numeric_pattern_token("256") is None


def test_validate_numeric_pattern_token_ignores_non_numeric_tokens(validate_golden_qa_module) -> None:
    mod = validate_golden_qa_module
    assert mod.validate_numeric_pattern_token("ImageNet") is None
    assert mod.validate_numeric_pattern_token("Adam") is None


def test_validate_stem_detail_gold_requires_nonempty_patterns(validate_golden_qa_module) -> None:
    mod = validate_golden_qa_module
    errors = mod.validate_stem_detail_gold("stem-case", {"required_patterns": []})
    assert any("non-empty" in err for err in errors)


def test_validate_stem_detail_gold_requires_numeric_anchor(validate_golden_qa_module) -> None:
    mod = validate_golden_qa_module
    errors = mod.validate_stem_detail_gold(
        "stem-case",
        {"required_patterns": ["ImageNet", "Adam"]},
    )
    assert any("numeric required_pattern" in err for err in errors)


def test_validate_stem_detail_gold_accepts_repo_style_gold(validate_golden_qa_module) -> None:
    mod = validate_golden_qa_module
    errors = mod.validate_stem_detail_gold(
        "stem-001-q13",
        {"required_patterns": ["78.5%", "ImageNet", "0.001"]},
    )
    assert errors == []


def test_validate_fails_on_typo_chunk_id(tmp_path: Path, validate_golden_qa_module) -> None:
    mod = validate_golden_qa_module
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    golden_path = tmp_path / "golden.json"
    golden_path.write_text(
        json.dumps(
            {
                "version": "test",
                "items": [
                    {
                        "id": "bad-chunk",
                        "question": "typo chunk test",
                        "paradigm": "STEM",
                        "paper_id": "stem-001",
                        "scale": "detail",
                        "gold": {
                            "nodes": ["n_method"],
                            "edges": [],
                            "paragraphs": ["stem_001:chunk:42"],
                            "required_patterns": ["78.5%"],
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    (manifest_dir / "stem-001.json").write_text(
        json.dumps({"paper_id": "stem-001", "chunk_ids": ["stem-001:chunk:42"]}),
        encoding="utf-8",
    )
    args = mod.parse_args(
        [
            "--golden-file",
            str(golden_path),
            "--graph-dir",
            str(graph_dir),
            "--chunk-manifest-dir",
            str(manifest_dir),
            "--mock-vector-file",
            str(REPO_ROOT / "data" / "mock_vector_store.json"),
        ],
    )
    assert mod.validate(args) == mod.EXIT_VALIDATION_FAILED


def test_validate_script_passes_on_repo_golden_set(validate_golden_qa_module, tmp_path: Path) -> None:
    mod = validate_golden_qa_module
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    args = mod.parse_args(["--graph-dir", str(graph_dir)])
    assert mod.validate(args) == mod.EXIT_SUCCESS
