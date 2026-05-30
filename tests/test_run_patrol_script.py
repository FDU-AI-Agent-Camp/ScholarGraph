"""Unit tests for scripts/run_patrol.py helpers and CLI surface."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import RUN_PATROL_SCRIPT

REPO_ROOT = RUN_PATROL_SCRIPT.parents[1]
SCRIPT_PATH = RUN_PATROL_SCRIPT


def test_run_patrol_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--paper-ids" in result.stdout
    assert "--seed-demo-graphs" in result.stdout


def test_parse_args_defaults(run_patrol_module) -> None:
    args = run_patrol_module.parse_args([])
    assert args.paper_ids == "hss-001,hss-002"
    assert args.mode == "lens_clash"
    assert args.seed_demo_graphs is False


def test_resolve_paper_ids_requires_exactly_two(run_patrol_module) -> None:
    with pytest.raises(ValueError, match="恰好 2 篇"):
        run_patrol_module.resolve_paper_ids("hss-001")


async def test_main_success_with_seed_demo_graphs(run_patrol_module, tmp_path: Path) -> None:
    graph_dir = tmp_path / "graphs"
    exit_code = await run_patrol_module.async_main(
        [
            "--paper-ids",
            "hss-001,hss-002",
            "--graph-dir",
            str(graph_dir),
            "--seed-demo-graphs",
            "--compact",
        ],
    )
    assert exit_code == 0
    assert (graph_dir / "hss-001.json").is_file()
    assert (graph_dir / "hss-002.json").is_file()


async def test_main_returns_patrol_failed_exit(run_patrol_module, tmp_path: Path) -> None:
    graph_dir = tmp_path / "empty"
    exit_code = await run_patrol_module.async_main(
        [
            "--paper-ids",
            "hss-001,hss-002",
            "--graph-dir",
            str(graph_dir),
        ],
    )
    assert exit_code == 1


async def test_main_returns_usage_exit_on_invalid_paper_ids(run_patrol_module) -> None:
    exit_code = await run_patrol_module.async_main(["--paper-ids", "only-one"])
    assert exit_code == 2


def test_main_sync_wrapper_returns_exit_code(run_patrol_module, tmp_path: Path) -> None:
    graph_dir = tmp_path / "graphs"
    exit_code = run_patrol_module.main(
        [
            "--paper-ids",
            "hss-001,hss-002",
            "--graph-dir",
            str(graph_dir),
            "--seed-demo-graphs",
            "--compact",
        ],
    )
    assert exit_code == 0


def test_cli_subprocess_runs_patrol_with_seed(tmp_path: Path) -> None:
    graph_dir = tmp_path / "graphs"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--paper-ids",
            "hss-001,hss-002",
            "--graph-dir",
            str(graph_dir),
            "--seed-demo-graphs",
            "--compact",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip())
    assert payload["mode"] == "lens_clash"
    assert len(payload["insights"]) >= 1


def test_execute_patrol_prints_openapi_shape(run_patrol_module, tmp_path: Path, capsys) -> None:
    import asyncio

    graph_dir = tmp_path / "graphs"

    async def _run() -> None:
        report = await run_patrol_module.execute_patrol(
            ["hss-001", "hss-002"],
            run_patrol_module.PatrolMode.LENS_CLASH,
            graph_dir=graph_dir,
            seed_demo_graphs=True,
        )
        run_patrol_module.print_report(report, compact=True)

    asyncio.run(_run())
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["mode"] == "lens_clash"
    assert len(payload["insights"]) >= 1
