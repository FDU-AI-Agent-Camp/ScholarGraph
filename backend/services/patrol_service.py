"""Community patrol service facade (BE-4 implements backend.patrol)."""

from functools import lru_cache

from backend.api.exceptions import ApiError
from backend.patrol.errors import PatrolError
from backend.patrol.service import run_patrol as patrol_run
from backend.schemas.patrol import PatrolMode, PatrolReport


class PatrolService:
    """Delegates patrol execution to BE-4 run_patrol orchestration."""

    async def run_patrol(
        self,
        paper_ids: list[str],
        mode: PatrolMode = PatrolMode.LENS_CLASH,
    ) -> PatrolReport:
        try:
            return await patrol_run(paper_ids, mode)
        except PatrolError as exc:
            raise ApiError(
                exc.code,
                exc.message,
                status_code=exc.status_code,
            ) from exc


@lru_cache
def get_patrol_service() -> PatrolService:
    return PatrolService()
