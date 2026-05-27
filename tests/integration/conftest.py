"""Fixtures for tests/integration/."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.graph.workflow import get_compiled_paper_pipeline
from backend.schemas.paper import PaperDetail, PaperStatus
from backend.services.paper_service import get_paper_service


@pytest.fixture(autouse=True)
def clear_compiled_pipeline_cache() -> Iterator[None]:
    get_compiled_paper_pipeline.cache_clear()
    yield
    get_compiled_paper_pipeline.cache_clear()


@pytest.fixture
def integration_paper(tmp_path: Path) -> tuple[str, Path]:
    paper_id = "integration-mock-paper"
    pdf_path = tmp_path / f"{paper_id}.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% integration mock")

    now = datetime.now(UTC)
    service = get_paper_service()
    service._papers[paper_id] = PaperDetail(
        paper_id=paper_id,
        title="integration mock",
        status=PaperStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    service._status.pop(paper_id, None)
    return paper_id, pdf_path
