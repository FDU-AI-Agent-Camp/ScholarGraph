"""Run the BE-2 paper graph extractor and emit validated JSON."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.agents import extract  # noqa: E402
from backend.schemas import Paradigm  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paradigm", choices=[paradigm.value for paradigm in Paradigm], required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="Full paper text or representative excerpt.")
    source.add_argument("--file", type=Path, help="UTF-8 text file to extract.")
    parser.add_argument("--out", type=Path, help="Optional output path for graph JSON.")
    return parser.parse_args()


async def _main() -> int:
    args = _parse_args()
    full_text = args.text if args.text is not None else args.file.read_text(encoding="utf-8")
    result = await extract(full_text, Paradigm(args.paradigm))
    json_payload = result.graph.model_dump_json(indent=2)
    if result.warnings:
        print(f"# warnings: {result.warnings}", file=sys.stderr)
    if args.out:
        args.out.write_text(json_payload + "\n", encoding="utf-8")
    else:
        print(json_payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
