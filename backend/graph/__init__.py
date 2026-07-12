"""Graph storage, query, GraphRAG, and LangGraph pipeline."""

from backend.graph.query import GraphQuery
from backend.graph.store import GraphStore


def __getattr__(name: str) -> object:
    """Lazily expose heavy symbols to break import cycles with llm.client."""
    if name in ("QaEvent", "qa_stream"):
        from backend.graph.qa import QaEvent, qa_stream

        return qa_stream if name == "qa_stream" else QaEvent
    if name in (
        "build_paper_pipeline_graph",
        "get_compiled_paper_pipeline",
        "pipeline_node_names",
        "run_paper_pipeline",
    ):
        from backend.graph.workflow import (
            build_paper_pipeline_graph,
            get_compiled_paper_pipeline,
            pipeline_node_names,
            run_paper_pipeline,
        )

        mapping = {
            "build_paper_pipeline_graph": build_paper_pipeline_graph,
            "get_compiled_paper_pipeline": get_compiled_paper_pipeline,
            "pipeline_node_names": pipeline_node_names,
            "run_paper_pipeline": run_paper_pipeline,
        }
        return mapping[name]
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


# pyright: ignore[reportUnsupportedDunderAll]
__all__ = [
    "build_paper_pipeline_graph",
    "get_compiled_paper_pipeline",
    "GraphQuery",
    "GraphStore",
    "pipeline_node_names",
    "QaEvent",
    "qa_stream",
    "run_paper_pipeline",
]
