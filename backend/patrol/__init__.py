"""Community patrol and Lens Clash (BE-4)."""

from backend.patrol.claim_evolution import build_claim_evolution_insight
from backend.patrol.contradiction import build_contradiction_insight
from backend.patrol.method_overlap import build_method_overlap_insight
from backend.patrol.samples import seed_all_demo_patrol_graphs, seed_corpus_patrol_graphs, seed_stem_patrol_graphs
from backend.patrol.service import run_patrol

__all__ = [
    "build_claim_evolution_insight",
    "build_contradiction_insight",
    "build_method_overlap_insight",
    "run_patrol",
    "seed_all_demo_patrol_graphs",
    "seed_corpus_patrol_graphs",
    "seed_stem_patrol_graphs",
]
