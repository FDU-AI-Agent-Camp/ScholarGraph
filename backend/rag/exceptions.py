# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Domain exceptions for RAG vector retrieval."""

from __future__ import annotations


class VectorStoreUnavailableError(Exception):
    """Raised when vector-store infrastructure fails (not merely missing index)."""

    def __init__(
        self,
        message: str,
        *,
        paper_id: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.paper_id = paper_id
        self.cause = cause
