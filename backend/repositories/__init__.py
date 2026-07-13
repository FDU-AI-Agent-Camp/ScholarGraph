"""Repository layer for ScholarGraph persistence."""

from backend.repositories.async_bridge import register_main_event_loop, run_async
from backend.repositories.paper_repository import PaperRepository, get_paper_repository
from backend.repositories.pipeline_repository import PipelineRepository, get_pipeline_repository

__all__ = [
    "PaperRepository",
    "PipelineRepository",
    "get_paper_repository",
    "get_pipeline_repository",
    "register_main_event_loop",
    "run_async",
]
