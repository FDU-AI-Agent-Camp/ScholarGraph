"""Health check endpoint."""

from fastapi import APIRouter, Depends

from backend.api.deps import get_request_id
from backend.api.responses import success
from backend.config import get_settings
from backend.constants import API_VERSION

router = APIRouter()


@router.get("/health")
async def health(request_id: str = Depends(get_request_id)) -> dict:
    """Liveness probe with LLM mode disclosure for FE banners."""
    settings = get_settings()
    return success(
        {
            "status": "ok",
            "version": API_VERSION,
            "llm_mode": settings.llm_mode,
            "llm_connected": settings.is_llm_live,
            "llm_note": (
                "Mock 模式：LLM 云服务尚未接入，问答/巡检返回本地模板。"
                if settings.is_llm_mock
                else "Live 模式：已配置真实 LLM 网关。"
            ),
        },
        request_id,
    )
