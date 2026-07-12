"""Pyright adversarial fixtures — prove VectorStoreProtocol blocks compile-time drift."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

_FIXTURES_DIR = REPO_ROOT / "tests" / "rag" / "fixtures" / "pyright_contract"

_PYRIGHT_PASS_FIXTURES = (
    "good_zero_type_penetration.py",
    "good_optional_top_k_boundaries.py",
)

_PYRIGHT_FAIL_FIXTURES = (
    ("bad_caller_unknown_kwarg.py", ("score_threshold",)),
    ("bad_caller_legacy_store_extra_kwarg.py", ("query_embedding",)),
    ("bad_store_wrong_return_type.py", ("VectorStoreProtocol",)),
    ("bad_store_missing_query_embedding.py", ("VectorStoreProtocol",)),
)


_FIXTURES_PROJECT = _FIXTURES_DIR / "pyrightconfig.json"


def _run_pyright_on_fixture(fixture_name: str) -> subprocess.CompletedProcess[str]:
    fixture_path = _FIXTURES_DIR / fixture_name
    assert fixture_path.is_file(), fixture_path
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pyright",
            "--project",
            str(_FIXTURES_PROJECT),
            str(fixture_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("fixture_name", _PYRIGHT_PASS_FIXTURES)
def test_pyright_passes_contract_aligned_fixtures(fixture_name: str) -> None:
    result = _run_pyright_on_fixture(fixture_name)
    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 0, combined


@pytest.mark.parametrize(
    ("fixture_name", "expected_fragments"),
    _PYRIGHT_FAIL_FIXTURES,
    ids=[name for name, _ in _PYRIGHT_FAIL_FIXTURES],
)
def test_pyright_catches_contract_drift(fixture_name: str, expected_fragments: tuple[str, ...]) -> None:
    result = _run_pyright_on_fixture(fixture_name)
    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0, combined
    for fragment in expected_fragments:
        assert fragment in combined, combined


def test_backend_ci_gate_runs_pyright_before_pytest() -> None:
    """Gate 1: develop PR workflow must block on ``pyright backend`` via ``make ci``."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    workflow = (REPO_ROOT / ".github" / "workflows" / "backend.yml").read_text(encoding="utf-8")
    check_backend = (REPO_ROOT / "scripts" / "check_backend.py").read_text(encoding="utf-8")

    assert "uv run pyright backend" in makefile
    assert "make ci" in workflow
    assert '"pyright"' in check_backend or "'pyright'" in check_backend
    pyright_step_index = check_backend.index("pyright")
    pytest_step_index = check_backend.index('"pytest"')
    assert pyright_step_index < pytest_step_index
