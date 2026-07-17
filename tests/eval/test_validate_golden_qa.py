# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

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


def test_validate_auto_seeds_builtin_hss_graph_when_missing(
    validate_golden_qa_module,
    tmp_path: Path,
) -> None:
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
                        "id": "hss-case",
                        "question": "核心论点",
                        "paradigm": "HSS",
                        "paper_id": "hss-001",
                        "scale": "summary",
                        "gold": {"nodes": ["n1"], "edges": []},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = mod.parse_args(["--golden-file", str(golden_path), "--graph-dir", str(graph_dir)])
    assert mod.validate(args) == mod.EXIT_SUCCESS
    assert (graph_dir / "hss-001.json").is_file()


def test_validate_unknown_paper_without_graph_exits_graph_not_ready(
    validate_golden_qa_module,
    tmp_path: Path,
) -> None:
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
                        "id": "unknown-case",
                        "question": "missing graph",
                        "paradigm": "HSS",
                        "paper_id": "unknown-999",
                        "scale": "summary",
                        "gold": {"nodes": ["n1"], "edges": []},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = mod.parse_args(
        ["--golden-file", str(golden_path), "--graph-dir", str(graph_dir), "--no-auto-seed"],
    )
    assert mod.validate(args) == mod.EXIT_GRAPH_NOT_READY


def test_validate_unknown_paper_allow_skip_exits_success(
    validate_golden_qa_module,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = validate_golden_qa_module
    monkeypatch.setattr(mod, "is_ci_environment", lambda: False)
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    golden_path = tmp_path / "golden.json"
    golden_path.write_text(
        json.dumps(
            {
                "version": "test",
                "items": [
                    {
                        "id": "unknown-case",
                        "question": "missing graph",
                        "paradigm": "HSS",
                        "paper_id": "unknown-999",
                        "scale": "summary",
                        "gold": {"nodes": ["n1"], "edges": []},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = mod.parse_args(
        [
            "--golden-file",
            str(golden_path),
            "--graph-dir",
            str(graph_dir),
            "--allow-skip",
        ],
    )
    assert mod.validate(args) == mod.EXIT_SUCCESS
    captured = capsys.readouterr()
    assert "[SKIP]" in captured.err
    assert "[SKIP]" not in captured.out


def test_validate_no_auto_seed_builtin_missing_exits_graph_not_ready(
    validate_golden_qa_module,
    tmp_path: Path,
) -> None:
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
                        "id": "hss-case",
                        "question": "核心论点",
                        "paradigm": "HSS",
                        "paper_id": "hss-001",
                        "scale": "summary",
                        "gold": {"nodes": ["n1"], "edges": []},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = mod.parse_args(
        ["--golden-file", str(golden_path), "--graph-dir", str(graph_dir), "--no-auto-seed"],
    )
    assert mod.validate(args) == mod.EXIT_GRAPH_NOT_READY


def test_build_validate_policy_defaults_strict(validate_golden_qa_module) -> None:
    mod = validate_golden_qa_module
    policy = mod.build_validate_policy(mod.parse_args([]))
    assert policy.strict is True
    assert policy.auto_seed is True
    assert policy.allow_skip is False


def test_build_validate_policy_no_strict_allows_skip(
    validate_golden_qa_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = validate_golden_qa_module
    monkeypatch.setattr(mod, "is_ci_environment", lambda: False)
    policy = mod.build_validate_policy(mod.parse_args(["--no-strict"]))
    assert policy.strict is False
    assert policy.allow_skip is True


def test_ci_environment_forces_strict_even_with_allow_skip(
    validate_golden_qa_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = validate_golden_qa_module
    monkeypatch.setenv("CI", "true")
    policy = mod.build_validate_policy(mod.parse_args(["--allow-skip"]))
    assert policy.strict is True
    assert policy.allow_skip is False


def test_exit_codes_document_data_drift_vs_infrastructure(validate_golden_qa_module) -> None:
    mod = validate_golden_qa_module
    assert mod.EXIT_SUCCESS == 0
    assert mod.EXIT_DATA_DRIFT == 1
    assert mod.EXIT_INFRASTRUCTURE_ERROR == 2
    assert mod.EXIT_VALIDATION_FAILED == mod.EXIT_DATA_DRIFT
    assert mod.EXIT_GRAPH_NOT_READY == mod.EXIT_INFRASTRUCTURE_ERROR


def test_missing_golden_file_returns_infrastructure_exit(
    validate_golden_qa_module,
    tmp_path: Path,
) -> None:
    mod = validate_golden_qa_module
    args = mod.parse_args(["--golden-file", str(tmp_path / "missing.json"), "--graph-dir", str(tmp_path)])
    assert mod.validate(args) == mod.EXIT_INFRASTRUCTURE_ERROR


def test_stale_node_id_returns_data_drift_exit(
    validate_golden_qa_module,
    tmp_path: Path,
) -> None:
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
                        "id": "stale-node",
                        "question": "bad node",
                        "paradigm": "HSS",
                        "paper_id": "hss-001",
                        "scale": "summary",
                        "gold": {"nodes": ["does-not-exist"], "edges": []},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = mod.parse_args(["--golden-file", str(golden_path), "--graph-dir", str(graph_dir)])
    assert mod.validate(args) == mod.EXIT_DATA_DRIFT


def test_ci_environment_ignores_allow_skip_for_unknown_paper(
    validate_golden_qa_module,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = validate_golden_qa_module
    monkeypatch.setenv("CI", "true")
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    golden_path = tmp_path / "golden.json"
    golden_path.write_text(
        json.dumps(
            {
                "version": "test",
                "items": [
                    {
                        "id": "unknown-case",
                        "question": "missing graph",
                        "paradigm": "HSS",
                        "paper_id": "unknown-999",
                        "scale": "summary",
                        "gold": {"nodes": ["n1"], "edges": []},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = mod.parse_args(
        ["--golden-file", str(golden_path), "--graph-dir", str(graph_dir), "--allow-skip"],
    )
    assert mod.validate(args) == mod.EXIT_GRAPH_NOT_READY


def test_resolve_exit_code_priority_infrastructure_over_data_drift(
    validate_golden_qa_module,
) -> None:
    mod = validate_golden_qa_module
    assert mod.resolve_exit_code(graph_not_ready=True, all_valid=True) == mod.EXIT_INFRASTRUCTURE_ERROR
    assert mod.resolve_exit_code(graph_not_ready=True, all_valid=False) == mod.EXIT_INFRASTRUCTURE_ERROR
    assert mod.resolve_exit_code(graph_not_ready=False, all_valid=False) == mod.EXIT_DATA_DRIFT
    assert mod.resolve_exit_code(graph_not_ready=False, all_valid=True) == mod.EXIT_SUCCESS


def test_validate_mixed_fault_matrix_scans_all_items_and_returns_exit_2(
    validate_golden_qa_module,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Combo: Case A ok + Case B drift + Case C infra → full scan, exit 2 wins."""
    from backend.graph.qa_samples import load_m2_demo_graph, seed_m2_qa_graph
    from backend.graph.store import GraphStore

    mod = validate_golden_qa_module
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    seed_m2_qa_graph(graph_dir, paper_id="hss-001")
    GraphStore(base_dir=graph_dir).save(load_m2_demo_graph().model_copy(update={"paper_id": "hss-002"}))

    golden_path = tmp_path / "fault-matrix.json"
    golden_path.write_text(
        json.dumps(
            {
                "version": "fault-matrix",
                "items": [
                    {
                        "id": "case-a-ok",
                        "question": "valid hss-001",
                        "paradigm": "HSS",
                        "paper_id": "hss-001",
                        "scale": "summary",
                        "gold": {"nodes": ["n1"], "edges": []},
                    },
                    {
                        "id": "case-b-drift",
                        "question": "stale node on hss-002",
                        "paradigm": "HSS",
                        "paper_id": "hss-002",
                        "scale": "summary",
                        "gold": {"nodes": ["wrong-node-id"], "edges": []},
                    },
                    {
                        "id": "case-c-infra",
                        "question": "missing stem graph",
                        "paradigm": "STEM",
                        "paper_id": "stem-001",
                        "scale": "summary",
                        "gold": {"nodes": ["n_method"], "edges": []},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = mod.parse_args(
        [
            "--strict",
            "--no-auto-seed",
            "--golden-file",
            str(golden_path),
            "--graph-dir",
            str(graph_dir),
        ],
    )
    exit_code = mod.validate(args)
    captured = capsys.readouterr()

    assert exit_code == mod.EXIT_INFRASTRUCTURE_ERROR
    assert "wrong-node-id" in captured.err
    assert "case-b-drift" in captured.err
    assert "case-c-infra" in captured.err
    assert "Data Drift Error" in captured.err
    assert "Infrastructure Error" in captured.err
    assert "node_id='n1'" not in captured.err


def _write_stem_only_golden(path: Path, *, item_id: str = "stem-case") -> None:
    path.write_text(
        json.dumps(
            {
                "version": "corrupt-boundary",
                "items": [
                    {
                        "id": item_id,
                        "question": "stem graph boundary",
                        "paradigm": "STEM",
                        "paper_id": "stem-001",
                        "scale": "summary",
                        "gold": {"nodes": ["n_method"], "edges": []},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_load_paper_graph_safe_empty_file_reports_path(
    validate_golden_qa_module,
    tmp_path: Path,
) -> None:
    mod = validate_golden_qa_module
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    corrupt_path = graph_dir / "stem-001.json"
    corrupt_path.write_bytes(b"")

    graph, error = mod.load_paper_graph_safe("stem-001", graph_dir=graph_dir)

    assert graph is None
    assert error is not None
    assert "0 bytes" in error
    assert str(corrupt_path) in error


def test_load_paper_graph_safe_corrupt_json_reports_path(
    validate_golden_qa_module,
    tmp_path: Path,
) -> None:
    mod = validate_golden_qa_module
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    corrupt_path = graph_dir / "stem-001.json"
    corrupt_path.write_text('{"nodes": [missing_comma', encoding="utf-8")

    graph, error = mod.load_paper_graph_safe("stem-001", graph_dir=graph_dir)

    assert graph is None
    assert error is not None
    assert "invalid JSON" in error
    assert str(corrupt_path) in error


def test_validate_zero_byte_graph_exits_infrastructure_error(
    validate_golden_qa_module,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = validate_golden_qa_module
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    corrupt_path = graph_dir / "stem-001.json"
    corrupt_path.write_bytes(b"")
    golden_path = tmp_path / "golden.json"
    _write_stem_only_golden(golden_path)

    args = mod.parse_args(
        [
            "--strict",
            "--no-auto-seed",
            "--golden-file",
            str(golden_path),
            "--graph-dir",
            str(graph_dir),
        ],
    )
    exit_code = mod.validate(args)
    captured = capsys.readouterr()

    assert exit_code == mod.EXIT_INFRASTRUCTURE_ERROR
    assert "0 bytes" in captured.err
    assert str(corrupt_path) in captured.err
    assert "Infrastructure Error" in captured.err
    assert "Traceback" not in captured.err


def test_validate_corrupt_json_graph_exits_infrastructure_error(
    validate_golden_qa_module,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = validate_golden_qa_module
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    corrupt_path = graph_dir / "stem-001.json"
    corrupt_path.write_text('{"nodes": [missing_comma', encoding="utf-8")
    golden_path = tmp_path / "golden.json"
    _write_stem_only_golden(golden_path, item_id="stem-corrupt")

    args = mod.parse_args(
        [
            "--strict",
            "--no-auto-seed",
            "--golden-file",
            str(golden_path),
            "--graph-dir",
            str(graph_dir),
        ],
    )
    exit_code = mod.validate(args)
    captured = capsys.readouterr()

    assert exit_code == mod.EXIT_INFRASTRUCTURE_ERROR
    assert "invalid JSON" in captured.err
    assert str(corrupt_path) in captured.err
    assert "Infrastructure Error" in captured.err
    assert "Traceback" not in captured.err


def test_validate_success_routes_info_and_ok_to_stdout(
    validate_golden_qa_module,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = validate_golden_qa_module
    graph_dir = tmp_path / "graphs"
    args = mod.parse_args(["--strict", "--graph-dir", str(graph_dir)])
    exit_code = mod.validate(args)
    captured = capsys.readouterr()

    assert exit_code == mod.EXIT_SUCCESS
    assert "[INFO]" in captured.out
    assert "[OK]" in captured.out
    assert "[OK]" not in captured.err
    assert "❌ FAIL" not in captured.out


def test_validate_data_drift_routes_failures_to_stderr(
    validate_golden_qa_module,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = validate_golden_qa_module
    graph_dir = tmp_path / "graphs"
    golden_path = tmp_path / "golden.json"
    golden_path.write_text(
        json.dumps(
            {
                "version": "stream-routing",
                "items": [
                    {
                        "id": "stale-node",
                        "question": "bad node",
                        "paradigm": "HSS",
                        "paper_id": "hss-001",
                        "scale": "summary",
                        "gold": {"nodes": ["does-not-exist"], "edges": []},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = mod.parse_args(
        ["--strict", "--golden-file", str(golden_path), "--graph-dir", str(graph_dir)],
    )
    exit_code = mod.validate(args)
    captured = capsys.readouterr()

    assert exit_code == mod.EXIT_DATA_DRIFT
    assert "❌ FAIL" in captured.err
    assert "Data Drift Error" in captured.err
    assert "❌ FAIL" not in captured.out
    assert "Data Drift Error" not in captured.out
    assert "[INFO]" in captured.out
