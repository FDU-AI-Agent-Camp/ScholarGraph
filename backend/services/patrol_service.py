"""Community patrol service (BE-4 implements logic)."""

import json
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from backend.schemas.patrol import PatrolInsight, PatrolReport

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "docs" / "api" / "fixtures"


class PatrolService:
    """Skeleton: returns fixture report until BE-4 wires real patrol."""

    async def run_patrol(self, paper_ids: list[str]) -> PatrolReport:
        fixture_path = FIXTURES_DIR / "patrol-lens-clash.json"
        if fixture_path.is_file():
            payload = json.loads(fixture_path.read_text(encoding="utf-8"))
            data = payload["data"]
            insights = [
                PatrolInsight(
                    insight_id=item["insight_id"],
                    title=item["title"],
                    summary=item["summary"],
                    severity="warning",
                    paper_ids=item.get("paper_ids") or paper_ids,
                )
                for item in data.get("insights", [])
            ]
            return PatrolReport(
                report_id="mock-patrol",
                title=str(data.get("mode", "共同体巡检")),
                insights=insights,
            )
        return PatrolReport(
            report_id=str(uuid4()),
            title="共同体巡检（骨架占位）",
            insights=[],
        )


@lru_cache
def get_patrol_service() -> PatrolService:
    return PatrolService()
