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
    """Thread-safe paper_id → in-flight run_id map with revoke set."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inflight: dict[str, str] = {}
        self._revoked: set[tuple[str, str]] = set()

    def begin(self, paper_id: str, run_id: str) -> None:
        """Mark ``run_id`` as the current attempt for ``paper_id``."""
        with self._lock:
            self._inflight[paper_id] = run_id
            self._revoked.discard((paper_id, run_id))

    def revoke(self, paper_id: str, run_id: str | None = None) -> str | None:
        """Revoke current or explicit run; return the revoked run_id if known."""
        with self._lock:
            target = run_id or self._inflight.get(paper_id)
            if target is None:
                return None
            self._revoked.add((paper_id, target))
            self._trim_revoked_unlocked()
            if self._inflight.get(paper_id) == target:
                del self._inflight[paper_id]
            return target

    def may_activate(self, paper_id: str, run_id: str) -> bool:
        """Return False when the attempt was revoked (timeout / cancel)."""
        with self._lock:
            return (paper_id, run_id) not in self._revoked

    def clear(self, paper_id: str, run_id: str) -> None:
        """Drop inflight/revoked entries after successful activate or cleanup."""
        with self._lock:
            if self._inflight.get(paper_id) == run_id:
                del self._inflight[paper_id]
            self._revoked.discard((paper_id, run_id))

    def peek_inflight(self, paper_id: str) -> str | None:
        with self._lock:
            return self._inflight.get(paper_id)

    def reset(self) -> None:
        """Test helper: clear all state."""
        with self._lock:
            self._inflight.clear()
            self._revoked.clear()

    def _trim_revoked_unlocked(self) -> None:
        if len(self._revoked) <= _MAX_REVOKED_ENTRIES:
            return
        # Drop arbitrary oldest-ish entries by rebuilding from a sliced list.
        keep = list(self._revoked)[-(_MAX_REVOKED_ENTRIES // 2) :]
        self._revoked = set(keep)


_REGISTRY = IndexingRunRegistry()


def get_indexing_run_registry() -> IndexingRunRegistry:
    """Process-wide registry used by VectorStore activate gates and handlers."""
    return _REGISTRY
