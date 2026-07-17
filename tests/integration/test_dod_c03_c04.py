# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""V1 DoD C-03 / C-04 — CLI 冒烟 + HTTP 链路前后端联调联试.

覆盖：功能真实可用、边界鲁棒、红灯异常（exit code / SSE error / 错误文案反馈）。
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest
from backend.config import get_settings
from backend.graph.qa_samples import M2_DEMO_PAPER_ID, M2_HSS_QUESTIONS, seed_m2_qa_graph
from backend.graph.store import GraphStore
from backend.llm.client import reset_llm_client_cache
from backend.patrol.samples import CORPUS_PATROL_LENSES, seed_corpus_patrol_graphs
from httpx import AsyncClient

from tests.api.conftest import assert_success_envelope
from tests.conftest import REPO_ROOT, RUN_PATROL_SCRIPT


@pytest.fixture
def patrol_graph_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated GRAPH_DATA_DIR for C-04 HTTP ↔ CLI parity."""
    graph_dir = tmp_path / "graphs"
    monkeypatch.setenv("GRAPH_DATA_DIR", str(graph_dir))
    get_settings.cache_clear()
    yield graph_dir
    get_settings.cache_clear()


RUN_QA_SCRIPT = REPO_ROOT / "scripts" / "run_qa.py"
_SUBPROCESS_TEXT_KW = {"text": True, "encoding": "utf-8", "errors": "replace"}


@pytest.fixture(autouse=True)
def _restore_graph_data_dir_after_qa_cli() -> None:
    """``run_qa.main_async`` mutates ``os.environ``; reset so later API tests see default graphs."""
    from backend.services.paper_service import get_paper_service

    original = os.environ.get("GRAPH_DATA_DIR")
    yield
    if original is None:
        os.environ.pop("GRAPH_DATA_DIR", None)
    else:
        os.environ["GRAPH_DATA_DIR"] = original
    get_settings.cache_clear()
    get_paper_service.cache_clear()


def _load_run_qa_module():
    spec = importlib.util.spec_from_file_location("run_qa", RUN_QA_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_qa"] = module
    spec.loader.exec_module(module)
    return module


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = "message"
    for line in body.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            payload = json.loads(line.split(":", 1)[1].strip())
            events.append((event_name, payload))
    return events


def _parse_patrol_cli_json(stdout: str) -> dict:
    return json.loads(stdout.strip())


# ---------------------------------------------------------------------------
# C-03 — BE-3 QA CLI
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c03_graph_dir_flag_binds_qa_stream_without_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Functional: ``--graph-dir`` 须生效，即使 GRAPH_DATA_DIR 指向空目录."""
    mod = _load_run_qa_module()
    graph_dir = tmp_path / "graphs"
    wrong_dir = tmp_path / "wrong"
    wrong_dir.mkdir()
    graph_dir.mkdir()
    seed_m2_qa_graph(graph_dir)

    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("GRAPH_DATA_DIR", str(wrong_dir))
    get_settings.cache_clear()
    reset_llm_client_cache()

    code = await mod.main_async(
        mod.parse_args(
            [
                M2_DEMO_PAPER_ID,
                "这篇论文做了什么？",
                "--graph-dir",
                str(graph_dir),
            ],
        ),
    )
    assert code == mod.EXIT_SUCCESS


@pytest.mark.asyncio
async def test_c03_smoke_m2_all_scales_emit_verifiable_citations(tmp_path: Path) -> None:
    """Functional: 三类尺度 citation 节点可对照 graph-hss fixture."""
    mod = _load_run_qa_module()
    graph_dir = tmp_path / "graphs"
    seed_m2_qa_graph(graph_dir)

    code = await mod.main_async(
        mod.parse_args(["--smoke-m2", "--seed-demo-graph", "--graph-dir", str(graph_dir)]),
    )
    assert code == mod.EXIT_SUCCESS

    graph = GraphStore(base_dir=graph_dir).load(M2_DEMO_PAPER_ID)
    assert graph is not None
    node_ids = {node.id for node in graph.nodes}
    assert "n1" in node_ids
    assert "n2" in node_ids
    assert "n_lens" in node_ids


@pytest.mark.asyncio
async def test_c03_red_graph_missing_emits_graph_not_found(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Red: 无图谱时 SSE error + CLI exit 1."""
    mod = _load_run_qa_module()
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    code = await mod.main_async(
        mod.parse_args([M2_DEMO_PAPER_ID, "问题？", "--graph-dir", str(empty_dir)]),
    )
    captured = capsys.readouterr()
    assert code == mod.EXIT_QA_FAILED
    assert "GRAPH_NOT_FOUND" in captured.out or "GRAPH_NOT_FOUND" in captured.err


def test_c03_verify_citation_rejects_unknown_node_id(tmp_path: Path) -> None:
    """Red: citation 指向不存在节点时 verify_citation 返回 False 并输出说明."""
    mod = _load_run_qa_module()
    graph_dir = tmp_path / "graphs"
    seed_m2_qa_graph(graph_dir)

    result = mod.QaRunResult(
        answer_text="mock",
        citations=[{"paper_id": M2_DEMO_PAPER_ID, "node_id": "ghost-node", "label": "不存在"}],
        error_code=None,
    )
    stderr = StringIO()
    sys.stderr = stderr
    try:
        ok = mod.verify_citation(result, graph_dir, M2_DEMO_PAPER_ID)
    finally:
        sys.stderr = sys.__stderr__

    assert ok is False
    assert "不在图谱中" in stderr.getvalue()


def test_c03_verify_citation_rejects_label_mismatch(tmp_path: Path) -> None:
    """Red: citation label 与图谱不一致时给出不匹配反馈."""
    mod = _load_run_qa_module()
    graph_dir = tmp_path / "graphs"
    seed_m2_qa_graph(graph_dir)

    result = mod.QaRunResult(
        answer_text="mock",
        citations=[{"paper_id": M2_DEMO_PAPER_ID, "node_id": "n1", "label": "错误标签"}],
        error_code=None,
    )
    stderr = StringIO()
    sys.stderr = stderr
    try:
        ok = mod.verify_citation(result, graph_dir, M2_DEMO_PAPER_ID)
    finally:
        sys.stderr = sys.__stderr__

    assert ok is False
    assert "label 不匹配" in stderr.getvalue()


def test_c03_cli_subprocess_single_turn_exits_zero(tmp_path: Path) -> None:
    """C-03 门禁命令：单轮问答 + seed."""
    graph_dir = tmp_path / "graphs"
    env = {
        **os.environ,
        "LLM_MODE": "mock",
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [
            sys.executable,
            str(RUN_QA_SCRIPT),
            M2_DEMO_PAPER_ID,
            "这篇论文做了什么？",
            "--seed-demo-graph",
            "--graph-dir",
            str(graph_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        env=env,
        **_SUBPROCESS_TEXT_KW,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "answer_id" in result.stdout


@pytest.mark.asyncio
async def test_c03_http_and_cli_citation_parity(
    api_client: AsyncClient,
    mock_llm_env: Path,
) -> None:
    """联调：HTTP SSE citation 与 CLI 单轮引用同一 graph-hss 节点."""
    mod = _load_run_qa_module()
    question = M2_HSS_QUESTIONS[0].question

    response = await api_client.post(
        f"/api/v1/papers/{M2_DEMO_PAPER_ID}/qa/stream",
        json={"question": question},
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    http_citation = next(payload for name, payload in _parse_sse(response.text) if name == "citation")

    code = await mod.main_async(
        mod.parse_args(
            [
                M2_DEMO_PAPER_ID,
                question,
                "--graph-dir",
                str(mock_llm_env),
            ],
        ),
    )
    assert code == mod.EXIT_SUCCESS

    graph = GraphStore(base_dir=mock_llm_env).load(M2_DEMO_PAPER_ID)
    assert graph is not None
    node = next(n for n in graph.nodes if n.id == http_citation["node_id"])
    assert http_citation["label"] == node.label
    assert http_citation["paper_id"] == M2_DEMO_PAPER_ID


# ---------------------------------------------------------------------------
# C-04 — Patrol CLI
# ---------------------------------------------------------------------------


def test_c04_smoke_patrol_alias_parses(run_patrol_module) -> None:
    args = run_patrol_module.parse_args(["--smoke-patrol"])
    assert args.smoke_patrol is True
    assert args.seed_demo_graphs is False


@pytest.mark.asyncio
async def test_c04_smoke_patrol_alias_seeds_and_succeeds(run_patrol_module, tmp_path: Path) -> None:
    """Functional: ``--smoke-patrol`` 等价于 seed + 巡检."""
    graph_dir = tmp_path / "graphs"
    exit_code = await run_patrol_module.async_main(
        [
            "--paper-ids",
            "hss-001,hss-002",
            "--graph-dir",
            str(graph_dir),
            "--smoke-patrol",
            "--compact",
        ],
    )
    assert exit_code == 0
    assert (graph_dir / "hss-001.json").is_file()
    assert (graph_dir / "hss-002.json").is_file()


def test_c04_cli_subprocess_smoke_patrol_compact_json(tmp_path: Path) -> None:
    """C-04 门禁命令：--seed-demo-graphs --smoke-patrol."""
    graph_dir = tmp_path / "graphs"
    result = subprocess.run(
        [
            sys.executable,
            str(RUN_PATROL_SCRIPT),
            "--seed-demo-graphs",
            "--smoke-patrol",
            "--graph-dir",
            str(graph_dir),
            "--compact",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        **_SUBPROCESS_TEXT_KW,
    )
    assert result.returncode == 0, result.stderr
    payload = _parse_patrol_cli_json(result.stdout)
    assert payload["mode"] == "lens_clash"
    assert payload["paper_ids"] == ["hss-001", "hss-002"]
    assert len(payload["insights"]) >= 1
    node_refs = payload["insights"][0]["node_refs"]
    assert len(node_refs) == 2
    assert node_refs[0]["node_id"] == CORPUS_PATROL_LENSES["hss-001"][0]
    assert node_refs[0]["label"] == CORPUS_PATROL_LENSES["hss-001"][1]


@pytest.mark.asyncio
async def test_c04_red_missing_graphs_exit_one_with_message(
    run_patrol_module,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Red: 无 seed 且图谱缺失 → exit 1 + PatrolError 文案."""
    graph_dir = tmp_path / "empty"
    exit_code = await run_patrol_module.async_main(
        [
            "--paper-ids",
            "hss-001,hss-002",
            "--graph-dir",
            str(graph_dir),
        ],
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err.strip()


@pytest.mark.asyncio
async def test_c04_red_invalid_paper_count_exit_two(run_patrol_module) -> None:
    """Red: paper_ids 数量非法 → exit 2."""
    exit_code = await run_patrol_module.async_main(["--paper-ids", "only-one"])
    assert exit_code == 2


@pytest.mark.asyncio
async def test_c04_http_patrol_matches_cli_after_seed(
    api_client: AsyncClient,
    patrol_graph_dir: Path,
) -> None:
    """联调：CLI seed 后 HTTP POST /patrol 与 CLI JSON node_refs 一致."""
    seed_corpus_patrol_graphs(patrol_graph_dir)

    cli_result = subprocess.run(
        [
            sys.executable,
            str(RUN_PATROL_SCRIPT),
            "--paper-ids",
            "hss-001,hss-002",
            "--graph-dir",
            str(patrol_graph_dir),
            "--compact",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        **_SUBPROCESS_TEXT_KW,
    )
    assert cli_result.returncode == 0, cli_result.stderr
    cli_payload = _parse_patrol_cli_json(cli_result.stdout)

    response = await api_client.post(
        "/api/v1/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
    )
    assert response.status_code == 200
    body = response.json()
    assert_success_envelope(body)
    http_insight = body["data"]["insights"][0]
    cli_insight = cli_payload["insights"][0]

    assert http_insight["insight_id"] == cli_insight["insight_id"]
    assert len(http_insight["node_refs"]) == len(cli_insight["node_refs"])
    for http_ref, cli_ref in zip(http_insight["node_refs"], cli_insight["node_refs"], strict=True):
        assert http_ref["paper_id"] == cli_ref["paper_id"]
        assert http_ref["node_id"] == cli_ref["node_id"]
        assert http_ref["label"] == cli_ref["label"]
