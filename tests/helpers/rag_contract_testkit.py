# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Stand-in for downstream RAG stores that hard-filter on ``index_run_id`` metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndexRunRecord:
    """One indexed artifact tagged with the active RAG run id."""

    record_id: str
    paper_id: str
    index_run_id: str
    payload: str


class IndexRunMetadataStore:
    """Minimal Chroma-like store for contract-drift tests (组员 A consumer shim)."""

    def __init__(self) -> None:
        self._records: list[IndexRunRecord] = []

    def upsert(
        self,
        *,
        paper_id: str,
        index_run_id: str,
        record_id: str,
        payload: str,
    ) -> None:
        self._records = [
            record for record in self._records if not (record.paper_id == paper_id and record.record_id == record_id)
        ]
        self._records.append(
            IndexRunRecord(
                record_id=record_id,
                paper_id=paper_id,
                index_run_id=index_run_id,
                payload=payload,
            ),
        )

    def filter_by_index_run_id(self, *, paper_id: str, index_run_id: str) -> list[IndexRunRecord]:
        """Simulate ``where={\"index_run_id\": run_id}`` hard filtering."""
        return [
            record for record in self._records if record.paper_id == paper_id and record.index_run_id == index_run_id
        ]
