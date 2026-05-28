"""Agent service facade (BE-2 implements backend.agents)."""

from functools import lru_cache

from backend.agents.classifier import classify
from backend.agents.extractor import extract
from backend.schemas.graph import UnifiedPaperGraph
from backend.schemas.paradigm import Paradigm, ParadigmClassification
from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError


class AgentService:
    """Paradigm classification and graph extraction."""

    async def classify_paradigm(self, classifier_input: str) -> ParadigmClassification:
        try:
            return await classify(classifier_input)
        except NotImplementedError as exc:
            raise ServiceError(PIPELINE_FAILED_CODE, str(exc)) from exc
        except Exception as exc:
            raise ServiceError("LLM_JSON_INVALID", f"范式分类失败: {exc}") from exc

    async def extract_graph(
        self,
        full_text: str,
        paradigm: Paradigm,
        *,
        paper_id: str,
    ) -> UnifiedPaperGraph:
        try:
            graph = await extract(full_text, paradigm)
        except NotImplementedError as exc:
            raise ServiceError(PIPELINE_FAILED_CODE, str(exc)) from exc
        except Exception as exc:
            raise ServiceError("LLM_JSON_INVALID", f"图谱抽取失败: {exc}") from exc
        return graph.model_copy(update={"paper_id": paper_id, "paradigm": paradigm})


@lru_cache
def get_agent_service() -> AgentService:
    return AgentService()
