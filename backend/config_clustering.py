"""Per-model / per-paradigm clustering similarity thresholds for Settings."""

from __future__ import annotations

# Different embedding models train with different vector-space densities.
# Hard-coding a single threshold would break when switching models, so we keep
# per-model defaults and allow explicit env overrides.
DEFAULT_EMBEDDING_MODEL_THRESHOLDS: dict[str, dict[str, float]] = {
    "bge-m3": {
        "similarity": 0.85,
        "knn": 0.75,
    },
    "text-embedding-3-small": {
        "similarity": 0.65,
        "knn": 0.55,
    },
    "default": {
        "similarity": 0.80,
        "knn": 0.70,
    },
}

# Per-paradigm, per-node-category similarity thresholds for semantic clustering.
# A single global threshold causes over-merging for Method nodes (too loose) and
# under-merging for Dataset nodes (too strict).  Categories are intentionally
# coarse-grained so the matrix stays small and maintainable; unknown types fall
# back to the "Concept" bucket.
DYNAMIC_CLUSTERING_THRESHOLDS: dict[str, dict[str, float]] = {
    "STEM": {
        "Method": 0.92,
        "Dataset": 0.82,
        "Metric": 0.88,
        "Baseline": 0.88,
        "Concept": 0.88,
    },
    "HSS": {
        "Method": 0.86,
        "Dataset": 0.80,
        "Concept": 0.82,
    },
}


def clustering_category(node_type: str) -> str:
    """Map a concrete node type to its coarse threshold category."""
    category_map: dict[str, str] = {
        "Method": "Method",
        "Dataset": "Dataset",
        "Metric": "Metric",
        "Baseline": "Baseline",
    }
    return category_map.get(node_type, "Concept")
