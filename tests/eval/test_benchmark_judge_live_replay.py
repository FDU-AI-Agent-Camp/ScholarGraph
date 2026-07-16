"""Optional live Judge CI path using snapshot replay (zero token cost)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from tests.conftest import REPO_ROOT
from tests.fixtures.qa_judge_snapshot import load_qa_judge_snapshot

_BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "benchmark_qa.py"


@pytest.fixture
def benchmark_qa_module():
    spec = importlib.util.spec_from_file_location("benchmark_qa_live_replay", _BENCHMARK_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["benchmark_qa_live_replay"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.live_judge
@pytest.mark.asyncio
async def test_benchmark_live_judge_replay_smoke(
    benchmark_qa_module,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay persisted Judge snapshot in CI without calling cloud Judge APIs."""
    mod = benchmark_qa_module
    graph_dir = tmp_path / "graphs"
    graph_dir.mkdir()
    mod.seed_m2_qa_graph(graph_dir)

    golden_path = tmp_path / "golden.json"
    golden_path.write_text(
        json.dumps(
            {
                "version": "test-live-replay",
                "allowed_recall_floor": 0.5,
                "items": [
                    {
                        "question": "STEM F1 是多少？",
                        "paradigm": "STEM",
                        "paper_id": "hss-001",
                        "scale": "detail",
                        "gold": {
                            "nodes": ["n1"],
                            "edges": [],
                            "required_patterns": ["15%"],
                            "forbidden_patterns": [],
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    snapshot = load_qa_judge_snapshot()
    compliant_answer = "F1 达到 15% 在 ImageNet 上验证，引用节点 [CITE:n1]。"

    async def _fake_run_single_qa(_paper_id: str, _question: str, **_kwargs: object) -> mod.QaResult:
        return mod.QaResult(
            question="STEM F1 是多少？",
            paper_id="hss-001",
            answer_text=compliant_answer,
            citations=[{"type": "node", "node_id": "n1"}],
            elapsed_ms=1,
            ttft_ms=1,
        )

    mod.run_single_qa = _fake_run_single_qa  # type: ignore[method-assign]
    monkeypatch.setenv("JUDGE_SNAPSHOT_REPLAY", "1")

    args = mod.parse_args(
        [
            "--golden-file",
            str(golden_path),
            "--graph-dir",
            str(graph_dir),
            "--concurrency",
            "1",
            "--output",
            str(tmp_path / "report.json"),
        ],
    )
    with patch.object(mod, "invoke_qa_judge", side_effect=lambda *_a, **_k: snapshot):
        exit_code = await mod.run_benchmark(args)

    assert exit_code == mod.EXIT_SUCCESS
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["summary"]["mean_hallucination_rate"] == 0.0
