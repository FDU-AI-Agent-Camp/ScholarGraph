# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Subprocess integration tests for scripts/validate_golden_qa.py exit codes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.conftest import REPO_ROOT

VALIDATE_SCRIPT = REPO_ROOT / "scripts" / "validate_golden_qa.py"
_SUBPROCESS_TEXT_KW = {"text": True, "encoding": "utf-8", "errors": "replace"}


def _subprocess_env(*, strip_ci: bool = False) -> dict[str, str]:
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "SCHOLARGRAPH_IGNORE_DOTENV": "1",
    }
    if strip_ci:
        env.pop("CI", None)
        env.pop("GITHUB_ACTIONS", None)
    return env


def _run_validate_cli(
    *cli_args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATE_SCRIPT), *cli_args],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        env=env or _subprocess_env(),
        **_SUBPROCESS_TEXT_KW,
    )


def _write_unknown_paper_golden(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": "cli-test",
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


def _write_stale_node_golden(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": "cli-test",
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


def test_cli_strict_missing_unknown_graph_returns_exit_code_2(tmp_path: Path) -> None:
    """Real shell: strict + unknown paper + empty graph dir → OS exit 2."""
    graph_dir = tmp_path / "empty_graphs"
    golden_path = tmp_path / "golden.json"
    _write_unknown_paper_golden(golden_path)

    result = _run_validate_cli(
        "--strict",
        "--no-auto-seed",
        "--golden-file",
        str(golden_path),
        "--graph-dir",
        str(graph_dir),
    )

    assert result.returncode == 2
    assert "Infrastructure Error" in result.stderr
    assert "Infrastructure Error" not in result.stdout


def test_cli_stale_node_id_returns_exit_code_1(tmp_path: Path) -> None:
    """Real shell: graph loaded but gold node missing → OS exit 1 (data drift)."""
    graph_dir = tmp_path / "graphs"
    golden_path = tmp_path / "golden.json"
    _write_stale_node_golden(golden_path)

    result = _run_validate_cli(
        "--strict",
        "--golden-file",
        str(golden_path),
        "--graph-dir",
        str(graph_dir),
    )

    assert result.returncode == 1
    assert "Data Drift Error" in result.stderr
    assert "Data Drift Error" not in result.stdout


def test_cli_repo_golden_auto_seed_returns_exit_code_0(tmp_path: Path) -> None:
    """Fresh clone path: empty graph dir + repo golden → auto-seed → OS exit 0."""
    graph_dir = tmp_path / "graphs"

    result = _run_validate_cli("--strict", "--graph-dir", str(graph_dir))

    assert result.returncode == 0
    assert (graph_dir / "hss-001.json").is_file()
    assert "[OK]" in result.stdout


def test_cli_allow_skip_unknown_paper_returns_exit_code_0(tmp_path: Path) -> None:
    """Local relaxed mode: --allow-skip must not raise OS exit when graph missing."""
    graph_dir = tmp_path / "graphs"
    golden_path = tmp_path / "golden.json"
    _write_unknown_paper_golden(golden_path)

    result = _run_validate_cli(
        "--allow-skip",
        "--no-auto-seed",
        "--golden-file",
        str(golden_path),
        "--graph-dir",
        str(graph_dir),
        env=_subprocess_env(strip_ci=True),
    )

    assert result.returncode == 0
    assert "[SKIP]" in result.stderr
    assert "[SKIP]" not in result.stdout


def test_cli_missing_golden_file_returns_exit_code_2(tmp_path: Path) -> None:
    result = _run_validate_cli(
        "--strict",
        "--golden-file",
        str(tmp_path / "missing-golden.json"),
        "--graph-dir",
        str(tmp_path / "graphs"),
    )

    assert result.returncode == 2
    assert "金标文件不存在" in result.stderr


def _seed_fault_matrix_graphs(graph_dir: Path) -> None:
    from backend.graph.qa_samples import load_m2_demo_graph, seed_m2_qa_graph
    from backend.graph.store import GraphStore

    seed_m2_qa_graph(graph_dir, paper_id="hss-001")
    GraphStore(base_dir=graph_dir).save(load_m2_demo_graph().model_copy(update={"paper_id": "hss-002"}))


def _write_fault_matrix_golden(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": "fault-matrix-cli",
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


def test_cli_mixed_fault_matrix_exit_code_2_overrides_drift(tmp_path: Path) -> None:
    """Subprocess combo: drift (1) + infra (2) in one golden file → OS exit 2 after full scan."""
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    _seed_fault_matrix_graphs(graph_dir)
    golden_path = tmp_path / "fault-matrix.json"
    _write_fault_matrix_golden(golden_path)

    result = _run_validate_cli(
        "--strict",
        "--no-auto-seed",
        "--golden-file",
        str(golden_path),
        "--graph-dir",
        str(graph_dir),
    )

    assert result.returncode == 2
    assert "case-b-drift" in result.stderr
    assert "case-c-infra" in result.stderr
    assert "wrong-node-id" in result.stderr
    assert "Data Drift Error" in result.stderr
    assert "Infrastructure Error" in result.stderr
    assert "node_id='n1'" not in result.stderr


def _write_stem_only_golden(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": "corrupt-boundary-cli",
                "items": [
                    {
                        "id": "stem-boundary",
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


def test_cli_zero_byte_graph_returns_exit_code_2(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    corrupt_path = graph_dir / "stem-001.json"
    corrupt_path.write_bytes(b"")
    golden_path = tmp_path / "golden.json"
    _write_stem_only_golden(golden_path)

    result = _run_validate_cli(
        "--strict",
        "--no-auto-seed",
        "--golden-file",
        str(golden_path),
        "--graph-dir",
        str(graph_dir),
    )

    assert result.returncode == 2
    assert "0 bytes" in result.stderr
    assert str(corrupt_path) in result.stderr
    assert "Infrastructure Error" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_corrupt_json_graph_returns_exit_code_2(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    corrupt_path = graph_dir / "stem-001.json"
    corrupt_path.write_text('{"nodes": [missing_comma', encoding="utf-8")
    golden_path = tmp_path / "golden.json"
    _write_stem_only_golden(golden_path)

    result = _run_validate_cli(
        "--strict",
        "--no-auto-seed",
        "--golden-file",
        str(golden_path),
        "--graph-dir",
        str(graph_dir),
    )

    assert result.returncode == 2
    assert "invalid JSON" in result.stderr
    assert str(corrupt_path) in result.stderr
    assert "Infrastructure Error" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_success_routes_progress_to_stdout_not_stderr(tmp_path: Path) -> None:
    """[INFO]/[OK] on stdout; stderr stays free of success summary."""
    graph_dir = tmp_path / "graphs"

    result = _run_validate_cli("--strict", "--graph-dir", str(graph_dir))

    assert result.returncode == 0
    assert "[OK]" in result.stdout
    assert "[INFO]" in result.stdout
    assert "[OK]" not in result.stderr
    assert "Data Drift Error" not in result.stdout
    assert "Infrastructure Error" not in result.stdout


def test_cli_data_drift_routes_failures_to_stderr_not_stdout(tmp_path: Path) -> None:
    """❌ FAIL and [FAIL] summary on stderr only."""
    graph_dir = tmp_path / "graphs"
    golden_path = tmp_path / "golden.json"
    _write_stale_node_golden(golden_path)

    result = _run_validate_cli(
        "--strict",
        "--golden-file",
        str(golden_path),
        "--graph-dir",
        str(graph_dir),
    )

    assert result.returncode == 1
    assert "❌ FAIL" in result.stderr
    assert "Data Drift Error" in result.stderr
    assert "❌ FAIL" not in result.stdout
    assert "Data Drift Error" not in result.stdout
    assert "[INFO]" in result.stdout


def test_cli_stdout_redirect_keeps_errors_visible_on_stderr(tmp_path: Path) -> None:
    """Simulate ``validate ... > log.txt``: progress in file, errors pierce stderr."""
    graph_dir = tmp_path / "graphs"
    golden_path = tmp_path / "golden.json"
    _write_stale_node_golden(golden_path)
    log_path = tmp_path / "log.txt"

    with log_path.open("w", encoding="utf-8") as log_file:
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATE_SCRIPT),
                "--strict",
                "--golden-file",
                str(golden_path),
                "--graph-dir",
                str(graph_dir),
            ],
            cwd=REPO_ROOT,
            stdout=log_file,
            stderr=subprocess.PIPE,
            check=False,
            env=_subprocess_env(),
            **_SUBPROCESS_TEXT_KW,
        )

    log_text = log_path.read_text(encoding="utf-8")
    stderr_text = result.stderr or ""

    assert result.returncode == 1
    assert "[INFO]" in log_text
    assert "[OK]" not in log_text
    assert "❌ FAIL" not in log_text
    assert "Data Drift Error" not in log_text
    assert "❌ FAIL" in stderr_text
    assert "Data Drift Error" in stderr_text


def test_cli_stdout_redirect_success_puts_ok_in_log_file(tmp_path: Path) -> None:
    """Success path: [OK] lands in redirected stdout file, not stderr."""
    graph_dir = tmp_path / "graphs"
    log_path = tmp_path / "log.txt"

    with log_path.open("w", encoding="utf-8") as log_file:
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATE_SCRIPT),
                "--strict",
                "--graph-dir",
                str(graph_dir),
            ],
            cwd=REPO_ROOT,
            stdout=log_file,
            stderr=subprocess.PIPE,
            check=False,
            env=_subprocess_env(),
            **_SUBPROCESS_TEXT_KW,
        )

    log_text = log_path.read_text(encoding="utf-8")
    stderr_text = result.stderr or ""

    assert result.returncode == 0
    assert "[OK]" in log_text
    assert "[FAIL]" not in log_text
    assert "Infrastructure Error" not in stderr_text
