"""MinerU optional extra availability checks (path-B short PDF)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from backend.ingest.mineru_backend import (
    MINERU_BINARY,
    is_mineru_available,
    resolve_mineru_binary,
)


def test_is_mineru_available_false_when_binary_missing() -> None:
    with patch("backend.ingest.mineru_backend.resolve_mineru_binary", return_value=None):
        assert is_mineru_available() is False


def test_is_mineru_available_true_when_binary_resolved() -> None:
    with patch(
        "backend.ingest.mineru_backend.resolve_mineru_binary",
        return_value="/fake/.venv/Scripts/mineru.exe",
    ):
        assert is_mineru_available() is True


def test_resolve_mineru_binary_prefers_path() -> None:
    with patch("backend.ingest.mineru_backend.shutil.which", return_value="/usr/bin/mineru"):
        assert resolve_mineru_binary() == "/usr/bin/mineru"


def test_resolve_mineru_binary_falls_back_to_venv_scripts(tmp_path: Path) -> None:
    fake_python = tmp_path / "python.exe"
    fake_python.write_text("", encoding="utf-8")
    mineru_exe = tmp_path / "mineru.exe"
    mineru_exe.write_text("", encoding="utf-8")

    with (
        patch("backend.ingest.mineru_backend.shutil.which", return_value=None),
        patch("backend.ingest.mineru_backend.sys.executable", str(fake_python)),
    ):
        assert resolve_mineru_binary() == str(mineru_exe)


def test_mineru_cli_help_when_extra_installed() -> None:
    """Smoke: ``uv sync --extra mineru`` should expose a working ``mineru`` CLI."""
    binary = resolve_mineru_binary()
    if binary is None:
        pytest.skip("MinerU 未安装：仓库根目录执行 uv sync --extra mineru")

    completed = subprocess.run(
        [binary, "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, (completed.stderr or completed.stdout)[:500]
    assert MINERU_BINARY in (completed.stdout + completed.stderr).lower() or "-p" in completed.stdout


@pytest.mark.parametrize(
    "installed",
    [True, False],
)
def test_is_mineru_available_matches_install_state(installed: bool) -> None:
    """Document expected coupling between resolve_mineru_binary and is_mineru_available."""
    path = r"D:\repo\.venv\Scripts\mineru.exe" if installed else None
    with patch("backend.ingest.mineru_backend.resolve_mineru_binary", return_value=path):
        assert is_mineru_available() is installed


def test_mineru_binary_lives_in_project_venv_when_installed() -> None:
    """When extra is synced via uv, binary should sit next to the active interpreter."""
    if not is_mineru_available():
        pytest.skip("MinerU 未安装：uv sync --extra mineru")

    binary = resolve_mineru_binary()
    assert binary is not None
    scripts_dir = Path(sys.executable).resolve().parent
    assert Path(binary).resolve().parent == scripts_dir
