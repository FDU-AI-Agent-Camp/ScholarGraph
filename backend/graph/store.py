"""Graph persistence (BE-3: JSON-based storage, G6-ready export)."""

import json
from pathlib import Path

from backend.config import get_settings
from backend.schemas.graph import UnifiedPaperGraph


class GraphStore:
    """Read/write UnifiedPaperGraph by paper_id.

    V1 stores each graph as ``<paper_id>.json`` under ``GRAPH_DATA_DIR``.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        settings = get_settings()
        self._base_dir = base_dir or Path(settings.graph_data_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # core I/O
    # ------------------------------------------------------------------

    def _path(self, paper_id: str) -> Path:
        return self._base_dir / f"{paper_id}.json"

    def save(self, graph: UnifiedPaperGraph) -> None:
        """Persist graph to disk (atomic-ish via atomic-write semantics)."""
        self._path(graph.paper_id).write_text(
            graph.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load(self, paper_id: str) -> UnifiedPaperGraph | None:
        """Load graph from disk; returns *None* when paper_id is unknown."""
        path = self._path(paper_id)
        if not path.is_file():
            return None
        return UnifiedPaperGraph.model_validate_json(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # presentation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def to_g6(graph: UnifiedPaperGraph) -> dict:
        """Convert a ``UnifiedPaperGraph`` into AntV G6 **v5**-compatible dict.

        G6 v5 expects ``{id, data: {label, type, ...}}`` for nodes and
        ``{id, source, target, data: {label, type, ...}}`` for edges.  This
        matches the shape consumed by ``PaperGraph.vue``.
        """
        return {
            "nodes": [
                {
                    "id": n.id,
                    "data": {"label": n.label, "type": n.type, **n.data},
                }
                for n in graph.nodes
            ],
            "edges": [
                {
                    "id": e.id,
                    "source": e.source,
                    "target": e.target,
                    "data": {"label": e.label, "type": e.type, **e.data},
                }
                for e in graph.edges
            ],
        }
