"""Health check endpoint."""

from fastapi import APIRouter, Depends

from backend.api.deps import get_request_id
from backend.api.responses import success
from backend.config import get_settings
from backend.constants import API_VERSION
from backend.ingest.grobid_client import check_grobid_isalive

router = APIRouter()


@router.get("/health")
async def health(request_id: str = Depends(get_request_id)) -> dict:
    """Liveness probe with LLM mode disclosure for FE banners."""
    settings = get_settings()
    grobid_connected = await check_grobid_isalive(settings=settings)
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
            "grobid_url": settings.grobid_url,
            "grobid_connected": grobid_connected,
            "grobid_note": (
                "GROBID sidecar 可达，长档 path-B 可用。"
                if grobid_connected
                else "GROBID 不可达：长档 PDF 将降级为 PyMuPDF snippets。"
            ),
        },
        request_id,
    )
