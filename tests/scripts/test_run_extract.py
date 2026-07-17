# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""F.6 acceptance gate T12: scripts/run_extract.py CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from backend.agents.extract_constants import EXTRACT_HEURISTIC_FALLBACK_CODE
from backend.schemas.paradigm import Paradigm

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "run_extract.py"


def test_t12_run_extract_script_exists() -> None:
    assert SCRIPT.is_file()


@pytest.mark.asyncio
async def test_t12_run_extract_main_emits_graph_json_with_warnings_on_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.setenv("SCHOLARGRAPH_API_KEY", "test-key")
    monkeypatch.setenv("EXTRACT_LLM_ENABLED", "true")
    monkeypatch.setenv("EXTRACT_HEURISTIC_FALLBACK", "true")

    from backend.config import get_settings

    get_settings.cache_clear()

    import importlib.util

    spec = importlib.util.spec_from_file_location("run_extract", SCRIPT)
    assert spec and spec.loader
    run_extract_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_extract_module)

    async def _fake_extract(full_text: str, paradigm: Paradigm, **_kwargs):
        from backend.agents.extract_heuristic import extract_title
        from backend.agents.extractor import _fallback_to_heuristic

        return _fallback_to_heuristic(
            full_text,
            paradigm,
            paper_id="cli-paper",
            title=extract_title(full_text),
            reason="cli test",
        )

    with patch.object(run_extract_module, "extract", new=AsyncMock(side_effect=_fake_extract)):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "run_extract.py",
                "--paradigm",
                Paradigm.HSS.value,
                "--text",
                "标题：测试\n本文认为核心论点。",
            ],
        )
        assert await run_extract_module._main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["paradigm"] == Paradigm.HSS.value
    assert payload["nodes"]
    assert EXTRACT_HEURISTIC_FALLBACK_CODE in captured.err

    get_settings.cache_clear()


def test_t12_run_extract_cli_subprocess_live_fallback(tmp_path: Path) -> None:
    """Smoke: subprocess invocation exits 0 and prints valid JSON."""
    text_file = tmp_path / "sample.txt"
    text_file.write_text("标题：测试\n本文认为论点成立。", encoding="utf-8")
    out_file = tmp_path / "graph.json"

    env = {
        **__import__("os").environ,
        "LLM_MODE": "live",
        "SCHOLARGRAPH_API_KEY": "test-key",
        "EXTRACT_LLM_ENABLED": "true",
        "EXTRACT_HEURISTIC_FALLBACK": "true",
    }

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--paradigm",
            "HSS",
            "--file",
            str(text_file),
            "--out",
            str(out_file),
        ],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert out_file.is_file()
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert payload["paradigm"] == "HSS"
    assert payload["nodes"]
