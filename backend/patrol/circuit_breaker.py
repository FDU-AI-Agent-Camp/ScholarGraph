"""In-process circuit breaker for Patrol VectorStore access (P9 robustness)."""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum
from threading import Lock


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class VectorStoreCircuitBreaker:
    """Fail-fast guard after connectivity collapses (Chroma down / refused).

    When OPEN, callers skip heavy VectorStore I/O and degrade immediately.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 1,
        reset_timeout_seconds: float = 30.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._failure_threshold = max(1, failure_threshold)
        self._reset_timeout_seconds = reset_timeout_seconds
        self._clock = clock or time.monotonic
        self._failures = 0
        self._opened_at: float | None = None
        self._state = CircuitState.CLOSED
        self._lock = Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_half_open_unlocked()
            return self._state

    def allow_request(self) -> bool:
        """Return False when the breaker is OPEN (fast degrade path)."""
        with self._lock:
            self._maybe_half_open_unlocked()
            return self._state != CircuitState.OPEN

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None
            self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()

    def reset(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None
            self._state = CircuitState.CLOSED

    def _maybe_half_open_unlocked(self) -> None:
        if self._state != CircuitState.OPEN or self._opened_at is None:
            return
        if self._clock() - self._opened_at >= self._reset_timeout_seconds:
            self._state = CircuitState.HALF_OPEN
