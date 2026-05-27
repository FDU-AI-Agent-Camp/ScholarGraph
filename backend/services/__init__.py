"""Business services — workflow and API call these facades, not BE modules directly."""

from backend.services.agent_service import AgentService, get_agent_service
from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError
from backend.services.graph_persistence_service import (
    GraphPersistenceService,
    get_graph_persistence_service,
)
from backend.services.ingest_service import IngestService, get_ingest_service
from backend.services.paper_service import get_paper_service
from backend.services.pipeline_completion_service import (
    PipelineCompletionService,
    get_pipeline_completion_service,
)
from backend.services.pipeline_status_service import (
    PipelineStatusService,
    get_pipeline_status_service,
    validate_status_contract,
)

__all__ = [
    "AgentService",
    "GraphPersistenceService",
    "IngestService",
    "PipelineCompletionService",
    "PIPELINE_FAILED_CODE",
    "ServiceError",
    "get_agent_service",
    "get_graph_persistence_service",
    "get_ingest_service",
    "get_paper_service",
    "get_pipeline_completion_service",
    "PipelineStatusService",
    "get_pipeline_status_service",
    "validate_status_contract",
]
