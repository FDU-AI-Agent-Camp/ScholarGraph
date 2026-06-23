"""Probe the live LLM classifier on all corpus txt samples after prompt changes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.agents.classifier_heuristic import classify_heuristic
from backend.agents.classifier_llm import classify_with_llm
from backend.config import get_settings
from backend.ingest.snippets import build_classifier_input

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = REPO_ROOT / "data" / "corpus"


async def main() -> int:
    settings = get_settings()
    if not settings.is_llm_live:
        print("LLM_MODE is not live; skipping live LLM probe.")
        return 1

    samples = sorted(p.stem for p in CORPUS_DIR.glob("*.txt"))
    for sample_id in samples:
        text_path = CORPUS_DIR / f"{sample_id}.txt"
        full_text = text_path.read_text(encoding="utf-8")
        classifier_input = build_classifier_input(full_text)

        heuristic = classify_heuristic(classifier_input)
        llm = await classify_with_llm(classifier_input)

        print(f"\n{'=' * 80}")
        print(f"SAMPLE: {sample_id}")
        print(f"{'=' * 80}")
        print(
            json.dumps(
                {
                    "heuristic": heuristic.model_dump(),
                    "llm": llm.model_dump(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
