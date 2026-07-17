# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from backend.agents.extract_heuristic import extract_title
from backend.agents.extractor import _extract_two_phase
from backend.config import Settings
from backend.graph.store import GraphStore
from backend.schemas.paradigm import Paradigm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = Settings()
    paper_id = "hss-002"
    text = Path(f"data/corpus/{paper_id}.txt").read_text(encoding="utf-8")
    title = extract_title(text)
    logger.info("start %s chars=%d", paper_id, len(text))
    started = datetime.now(UTC)
    result = await _extract_two_phase(
        text,
        Paradigm.HSS,
        paper_id=paper_id,
        title=title,
        head_context=None,
        settings=settings,
    )
    elapsed = (datetime.now(UTC) - started).total_seconds()
    GraphStore().save(result.graph)
    logger.info(
        "done nodes=%d edges=%d elapsed=%.1f",
        len(result.graph.nodes),
        len(result.graph.edges),
        elapsed,
    )
    print(
        json.dumps(
            {
                "nodes": len(result.graph.nodes),
                "edges": len(result.graph.edges),
                "elapsed": elapsed,
                "warnings": result.warnings[-5:],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
