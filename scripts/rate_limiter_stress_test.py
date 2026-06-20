"""Rate limiter stress test using the hss-002 corpus (Slice 2).

Run with:
    uv run python scripts/rate_limiter_stress_test.py

Environment:
    LLM_MODE=live                      (required)
    EXTRACT_CHUNK_RPM_LIMIT=20         (default)
    EXTRACT_CHUNK_TPM_LIMIT=500000     (default)
    EXTRACT_CHUNK_MAX_CHARS=12000      (default)

Outputs a JSON report to data/tmp-test-graphs/rate_limiter_stress_report.json.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure live mode is intentional.
os.environ.setdefault("LLM_MODE", "live")
os.environ.setdefault("EXTRACT_CHUNK_RPM_LIMIT", "20")
os.environ.setdefault("EXTRACT_CHUNK_TPM_LIMIT", "500000")

# Must import after setting env defaults.
from backend.agents.extract_chunked import extract_chunked  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.llm.rate_limiter import AsyncTokenBucket, get_extract_rate_limiter  # noqa: E402
from backend.schemas.paradigm import Paradigm  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = REPO_ROOT / "data" / "corpus" / "hss-002.txt"
REPORT_DIR = REPO_ROOT / "data" / "tmp-test-graphs"
REPORT_PATH = REPORT_DIR / "rate_limiter_stress_report.json"


class InstrumentedTokenBucket(AsyncTokenBucket):
    """AsyncTokenBucket that records every acquire for stress analysis."""

    def __init__(self, rpm: int, tpm: int) -> None:
        super().__init__(rpm, tpm)
        self._events: list[dict[str, Any]] = []
        self._429_count = 0
        self._other_errors: list[str] = []

    async def acquire(self, *, tokens: int = 1, chars: int = 0) -> None:
        start = time.monotonic()
        try:
            await super().acquire(tokens=tokens, chars=chars)
            waited = time.monotonic() - start
            self._events.append(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "tokens": tokens,
                    "chars": chars,
                    "waited_s": round(waited, 4),
                    "ok": True,
                }
            )
        except Exception as exc:
            waited = time.monotonic() - start
            msg = str(exc)
            self._events.append(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "tokens": tokens,
                    "chars": chars,
                    "waited_s": round(waited, 4),
                    "ok": False,
                    "error": msg,
                }
            )
            if "429" in msg or "Too Many Requests" in msg:
                self._429_count += 1
            else:
                self._other_errors.append(msg)
            raise

    def report(self) -> dict[str, Any]:
        if not self._events:
            return {"events": 0, "429_count": 0}
        waits = [e["waited_s"] for e in self._events]
        return {
            "events": len(self._events),
            "429_count": self._429_count,
            "other_errors": self._other_errors,
            "total_wait_s": round(sum(waits), 2),
            "max_wait_s": round(max(waits), 4),
            "avg_wait_s": round(sum(waits) / len(waits), 4),
            "rpm": self.rpm,
            "tpm": self.tpm,
        }


def _instrument_rate_limiter(bucket: InstrumentedTokenBucket) -> Callable[[], AsyncTokenBucket]:
    def _factory() -> AsyncTokenBucket:
        return bucket

    return _factory


async def main() -> None:
    if not CORPUS_PATH.is_file():
        raise FileNotFoundError(f"Corpus not found: {CORPUS_PATH}")

    settings = get_settings()
    if settings.is_llm_mock:
        raise RuntimeError("Stress test requires LLM_MODE=live")

    rpm = settings.extract_chunk_rpm_limit
    tpm = settings.extract_chunk_tpm_limit
    logger.info("Starting rate limiter stress test")
    logger.info("Corpus: %s (%s bytes)", CORPUS_PATH, CORPUS_PATH.stat().st_size)
    logger.info("Rate limits: rpm=%s, tpm=%s", rpm, tpm)

    full_text = CORPUS_PATH.read_text(encoding="utf-8")
    logger.info("Text length: %s chars", len(full_text))

    bucket = InstrumentedTokenBucket(rpm=rpm, tpm=tpm)
    original_factory = get_extract_rate_limiter

    import backend.agents.extract_chunked as extract_chunked_module

    extract_chunked_module.get_extract_rate_limiter = _instrument_rate_limiter(bucket)

    paper_id = "stress-hss-002"
    started_at = time.monotonic()
    graph = None
    exception: str | None = None

    try:
        graph = await extract_chunked(
            full_text,
            Paradigm.HSS,
            paper_id=paper_id,
            title="当代中国电影的政治传播变迁研究",
            settings=settings,
        )
    except Exception as exc:
        logger.exception("Stress test extraction failed")
        exception = f"{type(exc).__name__}: {exc}"
    finally:
        elapsed = time.monotonic() - started_at
        extract_chunked_module.get_extract_rate_limiter = original_factory

    report: dict[str, Any] = {
        "started_at": datetime.fromtimestamp(started_at, UTC).isoformat(),
        "elapsed_s": round(elapsed, 2),
        "corpus": str(CORPUS_PATH),
        "corpus_chars": len(full_text),
        "paper_id": paper_id,
        "rate_limiter": bucket.report(),
        "graph": {
            "node_count": len(graph.nodes) if graph else 0,
            "edge_count": len(graph.edges) if graph else 0,
        }
        if graph is not None
        else None,
        "exception": exception,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Report written to %s", REPORT_PATH)
    if report["graph"]:
        logger.info(
            "Elapsed: %.2f s, nodes: %s, edges: %s",
            elapsed,
            report["graph"]["node_count"],
            report["graph"]["edge_count"],
        )
    else:
        logger.info("Elapsed: %.2f s, graph extraction failed", elapsed)
    logger.info("429 count: %s, other errors: %s", bucket._429_count, len(bucket._other_errors))

    if bucket._429_count:
        logger.error("RATE LIMITER STRESS TEST FAILED: %s HTTP 429 errors observed", bucket._429_count)
        raise SystemExit(1)
    if exception:
        logger.error("RATE LIMITER STRESS TEST FAILED: %s", exception)
        raise SystemExit(1)

    logger.info("RATE LIMITER STRESS TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
