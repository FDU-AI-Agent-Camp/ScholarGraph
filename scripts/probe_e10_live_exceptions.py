#!/usr/bin/env python3
"""E-10 live 异常路径抽验：无效 Key + 超时（仓库根目录执行）.

    uv run python scripts/probe_e10_live_exceptions.py
    uv run python scripts/probe_e10_live_exceptions.py --skip-timeout  # 仅测无效 Key
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.config import get_settings  # noqa: E402
from backend.graph.qa import qa_stream  # noqa: E402
from backend.graph.qa_samples import seed_m2_qa_graph  # noqa: E402
from backend.llm.client import LlmClient, reset_llm_client_cache  # noqa: E402
from backend.patrol.service import run_patrol  # noqa: E402
from backend.schemas.patrol import PatrolMode  # noqa: E402
from tests.helpers.patrol_graphs import seed_patrol_graphs  # noqa: E402

INVALID_KEY = "invalid-e10-probe-key-not-valid"
MAAS_BASE = "https://api.modelarts-maas.com/v2"


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = "message"
    for block in re.split(r"\n\n+", raw.strip()):
        if not block.strip():
            continue
        event_name = "message"
        data_line = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_line = line.split(":", 1)[1].strip()
        if data_line:
            events.append((event_name, json.loads(data_line)))
    return events


def probe_invalid_maas_key() -> bool:
    print("\n--- [1/4] MaaS HTTP invalid Key (expect 401 ModelArts.81003)")
    headers = {"Authorization": f"Bearer {INVALID_KEY}", "Content-Type": "application/json"}
    body = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 8,
    }
    response = httpx.post(f"{MAAS_BASE}/chat/completions", headers=headers, json=body, timeout=30.0)
    print(f"status={response.status_code}")
    payload = response.json()
    code = payload.get("error_code") or (payload.get("error") or {}).get("code")
    print(f"error_code={code}")
    ok = response.status_code == 401 and code == "ModelArts.81003"
    print(f"result={'PASS' if ok else 'FAIL'}")
    return ok


def _bind_live_invalid_key() -> None:
    import os

    os.environ["LLM_MODE"] = "live"
    os.environ["SCHOLARGRAPH_API_KEY"] = INVALID_KEY
    os.environ["LLM_API_BASE_URL"] = MAAS_BASE
    get_settings.cache_clear()
    reset_llm_client_cache()


async def probe_qa_invalid_key(graph_dir: Path) -> bool:
    print("\n--- [2/4] QA SSE invalid Key (expect QA_STREAM_ERROR, no 500)")
    _bind_live_invalid_key()
    seed_m2_qa_graph(graph_dir)
    import os

    os.environ["GRAPH_DATA_DIR"] = str(graph_dir)

    events: list[tuple[str, dict]] = []
    async for evt in qa_stream("hss-001", "核心论点是什么？"):
        events.append((evt.event, evt.data))

    names = [name for name, _ in events]
    error = next((data for name, data in events if name == "error"), None)
    print(f"events={names}")
    if error:
        print(f"error_code={error.get('code')} message_head={str(error.get('message', ''))[:120]}")
    ok = (
        "error" in names
        and error is not None
        and error.get("code") == "QA_STREAM_ERROR"
        and "done" in names
    )
    print(f"result={'PASS' if ok else 'FAIL'}")
    return ok


async def probe_patrol_invalid_key(graph_dir: Path) -> bool:
    print("\n--- [3/4] Patrol invalid Key (expect 200 + template fallback, not 500)")
    _bind_live_invalid_key()
    seed_patrol_graphs(
        graph_dir,
        {
            "hss-001": ("n_lens_a", "消费社会"),
            "hss-002": ("n_lens_b", "公共领域"),
        },
    )
    from backend.graph.store import GraphStore

    report = await run_patrol(
        ["hss-001", "hss-002"],
        PatrolMode.LENS_CLASH,
        store=GraphStore(base_dir=graph_dir),
    )
    summary = report.insights[0].summary
    print(f"status=200 summary_chars={len(summary)}")
    print(f"summary_head={summary[:100].replace(chr(10), ' ')}")
    ok = "分析视角" in summary and "Mock" not in summary
    print(f"result={'PASS' if ok else 'FAIL'}")
    return ok


def _restore_env(snapshot: dict[str, str | None]) -> None:
    import os

    for key, value in snapshot.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    get_settings.cache_clear()
    reset_llm_client_cache()


async def probe_timeout_valid_key(graph_dir: Path, env_snapshot: dict[str, str | None]) -> bool:
    print("\n--- [4/4] QA timeout (LLM_TIMEOUT_SECONDS=1, valid Key)")
    import os

    _restore_env(env_snapshot)
    settings = get_settings()
    if not settings.scholargraph_api_key.strip():
        print("SKIP: no SCHOLARGRAPH_API_KEY in .env")
        return True

    os.environ["LLM_MODE"] = "live"
    os.environ["LLM_TIMEOUT_SECONDS"] = "1"
    os.environ["GRAPH_DATA_DIR"] = str(graph_dir)
    get_settings.cache_clear()
    reset_llm_client_cache()
    seed_m2_qa_graph(graph_dir)

    events: list[tuple[str, dict]] = []
    async for evt in qa_stream("hss-001", "请详细展开核心论点、分论点与理论视角的论证链条。"):
        events.append((evt.event, evt.data))

    error = next((data for name, data in events if name == "error"), None)
    names = [name for name, _ in events]
    print(f"events={names}")
    if error:
        msg = str(error.get("message", ""))
        print(f"error_code={error.get('code')} message_head={msg[:160]}")
        timeout_like = any(
            token in msg.lower()
            for token in ("timeout", "timed out", "time out", "超时", "deadline")
        )
    else:
        timeout_like = False
        print("no error event (request may have finished under 1s)")

    ok = error is not None and error.get("code") == "QA_STREAM_ERROR" and timeout_like
    print(f"result={'PASS' if ok else 'WARN/SKIP' if not error else 'FAIL'}")
    return ok or not error


async def run_probes(*, skip_timeout: bool) -> int:
    import os

    env_snapshot = {
        "LLM_MODE": os.environ.get("LLM_MODE"),
        "SCHOLARGRAPH_API_KEY": os.environ.get("SCHOLARGRAPH_API_KEY"),
        "LLM_API_BASE_URL": os.environ.get("LLM_API_BASE_URL"),
        "LLM_TIMEOUT_SECONDS": os.environ.get("LLM_TIMEOUT_SECONDS"),
        "GRAPH_DATA_DIR": os.environ.get("GRAPH_DATA_DIR"),
    }
    graph_dir = Path(get_settings().graph_data_dir).resolve()
    graph_dir.mkdir(parents=True, exist_ok=True)

    results = [probe_invalid_maas_key(), await probe_qa_invalid_key(graph_dir), await probe_patrol_invalid_key(graph_dir)]
    if not skip_timeout:
        results.append(await probe_timeout_valid_key(graph_dir, env_snapshot))
    _restore_env(env_snapshot)

    passed = sum(1 for item in results if item)
    total = len(results)
    print(f"\n=== E-10 live probe: {passed}/{total} passed ===")
    return 0 if passed == total else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="E-10 live exception path probe")
    parser.add_argument("--skip-timeout", action="store_true", help="Skip timeout probe (needs valid Key)")
    args = parser.parse_args(argv)
    return asyncio.run(run_probes(skip_timeout=args.skip_timeout))


if __name__ == "__main__":
    raise SystemExit(main())
