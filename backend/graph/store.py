"""Graph persistence (BE-3 implements JSON/SQLite storage)."""

import json
from pathlib import Path

from backend.config import get_settings
from backend.schemas.graph import UnifiedPaperGraph


class GraphStore:
    """Read/write UnifiedPaperGraph by paper_id."""

    def __init__(self, base_dir: Path | None = None) -> None:
        settings = get_settings()
        self._base_dir = base_dir or Path(settings.graph_data_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, paper_id: str) -> Path:
        return self._base_dir / f"{paper_id}.json"

    def save(self, graph: UnifiedPaperGraph) -> None:
        self._path(graph.paper_id).write_text(
            graph.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load(self, paper_id: str) -> UnifiedPaperGraph | None:
        path = self._path(paper_id)
        if not path.is_file():
            return None
        return UnifiedPaperGraph.model_validate_json(path.read_text(encoding="utf-8"))
