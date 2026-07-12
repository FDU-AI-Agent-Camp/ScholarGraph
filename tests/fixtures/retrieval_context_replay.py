"""Load frozen RetrievalContext replay bundles for offline QA prompt tests."""

from __future__ import annotations

from pathlib import Path

from backend.rag.retrieval_context_io import RetrievalContextReplayBundle, load_replay_bundle

_FIXTURES_DIR = Path(__file__).resolve().parent
HSS_DETAIL_REPLAY_PATH = _FIXTURES_DIR / "retrieval_context_hss-001-detail.replay.json"


def load_hss_detail_replay_bundle() -> RetrievalContextReplayBundle:
    """Return the hss-001 DETAIL-scale offline replay bundle."""
    return load_replay_bundle(HSS_DETAIL_REPLAY_PATH)
