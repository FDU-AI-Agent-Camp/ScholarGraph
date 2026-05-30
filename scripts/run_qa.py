#!/usr/bin/env python
"""Demo script: run multi-scale QA over a stored paper graph.

Usage (from repo root)::

    uv run python scripts/run_qa.py <paper_id> "<question>"

Example::

    uv run python scripts/run_qa.py hss-001 "这篇论文的核心论点是什么？"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure repo root is on sys.path.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.graph.qa import qa_stream  # noqa: E402


async def main(paper_id: str, question: str) -> None:
    print(f"📄 paper_id : {paper_id}")
    print(f"❓ question : {question}")
    print("-" * 60)

    try:
        async for evt in qa_stream(paper_id, question):
            if evt.event == "message":
                sys.stdout.write(evt.data["delta"])
                sys.stdout.flush()
            elif evt.event == "citation":
                print(f"\n  📍 [CITE] node={evt.data['node_id']} → {evt.data['label']}")
            elif evt.event == "done":
                print(f"\n\n✅ answer_id = {evt.data.get('answer_id', '—')}")
            elif evt.event == "error":
                print(f"\n❌ {evt.data['code']}: {evt.data['message']}")
    except Exception as exc:
        print(f"\n💥 Unhandled: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: uv run python scripts/run_qa.py <paper_id> <question>")
        print('Example: uv run python scripts/run_qa.py hss-001 "这篇论文的核心论点是什么？"')
        sys.exit(2)

    pid = sys.argv[1]
    q = " ".join(sys.argv[2:])
    asyncio.run(main(pid, q))
