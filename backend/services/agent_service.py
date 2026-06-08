"""Agent service facade (BE-2 implements backend.agents)."""

from functools import lru_cache

from backend.agents.classifier import classify
from backend.agents.classifier_types import ClassifyResult
from backend.agents.extract_types import ExtractResult
from backend.agents.extractor import extract
from backend.schemas.paradigm import Paradigm
from backend.services.errors import PIPELINE_FAILED_CODE, ServiceError


class AgentService:
    """Paradigm classification and graph extraction."""

    async def classify_paradigm(self, classifier_input: str) -> ClassifyResult:
        try:
            return await classify(classifier_input)
        except ServiceError:
            raise
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
    ) -> ExtractResult:
        try:
            return await extract(full_text, paradigm, paper_id=paper_id)
        except ServiceError:
            raise
        except NotImplementedError as exc:
            raise ServiceError(PIPELINE_FAILED_CODE, str(exc)) from exc
        except Exception as exc:
            raise ServiceError("LLM_JSON_INVALID", f"图谱抽取失败: {exc}") from exc


@lru_cache
def get_agent_service() -> AgentService:
    return AgentService()
