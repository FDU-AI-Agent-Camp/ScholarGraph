# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Persist refined ingest head alongside graph JSON (P10 / P11)."""

from pathlib import Path

from backend.config import get_settings
from backend.schemas.ingest_head import IngestHead, PersistedHeadRefine


class HeadStore:
    """Read/write merged ingest head by paper_id.

    V1 stores each record as ``<paper_id>.head.json`` under ``GRAPH_DATA_DIR``.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        settings = get_settings()
        self._base_dir = base_dir or Path(settings.graph_data_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, paper_id: str) -> Path:
        return self._base_dir / f"{paper_id}.head.json"

    def save(
        self,
        paper_id: str,
        *,
        merged: IngestHead,
        classifier_input: str = "",
        warnings: list[str] | None = None,
    ) -> None:
        record = PersistedHeadRefine(
            paper_id=paper_id,
            merged=merged,
            classifier_input=classifier_input.strip(),
            warnings=list(warnings or ()),
        )
        self._path(paper_id).write_text(
            record.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load(self, paper_id: str) -> PersistedHeadRefine | None:
        path = self._path(paper_id)
        if not path.is_file():
            return None
        return PersistedHeadRefine.model_validate_json(path.read_text(encoding="utf-8"))

    def delete(self, paper_id: str) -> bool:
        """Remove persisted head refine record if it exists."""
        path = self._path(paper_id)
        if not path.is_file():
            return False
        path.unlink()
        return True
