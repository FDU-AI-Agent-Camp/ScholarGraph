"""In-process generation registry for RAG index runs (P13 orphan-thread hardening).

``asyncio.wait_for`` cancels the indexing coroutine but cannot kill ``to_thread``
workers already inside Chroma/embedding calls. This registry lets timeouts
*revoke* an in-flight ``run_id`` so a late worker cannot ``set_active_run_id``,
and supplies the id for compensating ``delete_run`` sweeps.
"""

from __future__ import annotations

import threading
from typing import Final

_MAX_REVOKED_ENTRIES: Final[int] = 4096


class IndexingRunRegistry:
    """Thread-safe paper_id → in-flight run_id map with ordered revoke set."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inflight: dict[str, str] = {}
        # Ordered set: insertion order preserved so sticky lookup returns latest.
        self._revoked: dict[tuple[str, str], None] = {}

    def begin(self, paper_id: str, run_id: str) -> None:
        """Mark ``run_id`` as the current attempt for ``paper_id``."""
        with self._lock:
            self._inflight[paper_id] = run_id
            self._revoked.pop((paper_id, run_id), None)

    def revoke(self, paper_id: str, run_id: str | None = None) -> str | None:
        """Revoke current or explicit run; return the revoked run_id if known.

        When ``wait_for`` cancels the replace coroutine first, inflight is already
        cleared and the run sits in ``_revoked``. A subsequent timeout-path
        ``revoke(paper_id)`` must still return that id so compensating cleanup can
        be scheduled. If several revoked ids exist for one paper, the **most
        recently revoked** id is returned (deterministic).
        """
        with self._lock:
            target = run_id or self._inflight.get(paper_id)
            if target is None:
                return self._latest_revoked_unlocked(paper_id)
            # Re-insert at end so sticky peek prefers this revoke as latest.
            self._revoked.pop((paper_id, target), None)
            self._revoked[(paper_id, target)] = None
            self._trim_revoked_unlocked()
            if self._inflight.get(paper_id) == target:
                del self._inflight[paper_id]
            return target

    def may_activate(self, paper_id: str, run_id: str) -> bool:
        """Return True only for the current non-revoked in-flight generation.

        Dual gate: must still be the registered ``inflight`` run **and** not in
        the sticky revoke set (covers superseded generations even if revoke was
        missed).
        """
        with self._lock:
            if (paper_id, run_id) in self._revoked:
                return False
            return self._inflight.get(paper_id) == run_id

    def clear(self, paper_id: str, run_id: str) -> None:
        """Drop inflight/revoked entries after successful activate or cleanup."""
        with self._lock:
            if self._inflight.get(paper_id) == run_id:
                del self._inflight[paper_id]
            self._revoked.pop((paper_id, run_id), None)

    def peek_inflight(self, paper_id: str) -> str | None:
        with self._lock:
            return self._inflight.get(paper_id)

    def reset(self) -> None:
        """Test helper: clear all state."""
        with self._lock:
            self._inflight.clear()
            self._revoked.clear()

    def _latest_revoked_unlocked(self, paper_id: str) -> str | None:
        latest: str | None = None
        for pid, rid in self._revoked:
            if pid == paper_id:
                latest = rid
        return latest

    def _trim_revoked_unlocked(self) -> None:
        if len(self._revoked) <= _MAX_REVOKED_ENTRIES:
            return
        # Keep the most recently inserted half (dict preserves insertion order).
        keep = list(self._revoked)[-(_MAX_REVOKED_ENTRIES // 2) :]
        self._revoked = {key: None for key in keep}


_REGISTRY = IndexingRunRegistry()


def get_indexing_run_registry() -> IndexingRunRegistry:
    """Process-wide registry used by VectorStore activate gates and handlers."""
    return _REGISTRY
