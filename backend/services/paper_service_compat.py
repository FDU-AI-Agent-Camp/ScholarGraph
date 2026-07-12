"""DB-backed dict-like shims for tests still migrating off in-memory PaperService state."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, MutableMapping
from pathlib import Path
from typing import TYPE_CHECKING

from backend.api.exceptions import ApiError
from backend.repositories import run_async
from backend.schemas.paper import PaperDetail, PaperStatus, PaperStatusData

if TYPE_CHECKING:
    from backend.services.paper_service import PaperService


class CompatPaperDict(MutableMapping[str, PaperDetail]):
    """Mutable ``_papers``-shaped view backed by ``PaperRepository``."""

    def __init__(self, service: PaperService) -> None:
        self._service = service

    def __getitem__(self, paper_id: str) -> PaperDetail:
        try:
            return run_async(self._service.get_paper(paper_id))
        except ApiError as err:
            if err.status_code == 404:
                raise KeyError(paper_id) from err
            raise

    def __setitem__(self, paper_id: str, detail: PaperDetail) -> None:
        self._service._upsert_compat_paper_detail(paper_id, detail)

    def __delitem__(self, paper_id: str) -> None:
        if not run_async(self._service._paper_repo.delete(paper_id)):
            raise KeyError(paper_id)

    def __iter__(self) -> Iterator[str]:
        items, _ = run_async(self._service._paper_repo.list(limit=10_000))
        return iter(paper.paper_id for paper in items)

    def __len__(self) -> int:
        _, total = run_async(self._service._paper_repo.list(limit=0))
        return total

    def get(self, paper_id: str, default: PaperDetail | None = None) -> PaperDetail | None:
        try:
            return self[paper_id]
        except KeyError:
            return default

    def pop(self, paper_id: str, default: PaperDetail | None = None) -> PaperDetail | None:
        try:
            detail = self[paper_id]
        except KeyError:
            if default is not None:
                return default
            raise
        del self[paper_id]
        return detail

    def keys(self) -> Iterable[str]:
        return list(self)


class CompatStatusDict(MutableMapping[str, PaperStatusData]):
    """Mutable ``_status``-shaped view backed by ``PipelineRepository``."""

    def __init__(self, service: PaperService) -> None:
        self._service = service

    def __getitem__(self, paper_id: str) -> PaperStatusData:
        snapshot = run_async(self._service._pipeline_repo.get_latest(paper_id))
        if snapshot is None:
            raise KeyError(paper_id)
        return snapshot

    def __setitem__(self, paper_id: str, snapshot: PaperStatusData) -> None:
        run_async(self._service._pipeline_repo.save_status(paper_id, snapshot))

    def __delitem__(self, paper_id: str) -> None:
        raise NotImplementedError("pipeline status rows are deleted via paper cascade")

    def __iter__(self) -> Iterator[str]:
        return iter(self._service._papers.keys())

    def __len__(self) -> int:
        return len(self._service._papers)

    def get(self, paper_id: str, default: PaperStatusData | None = None) -> PaperStatusData | None:
        try:
            return self[paper_id]
        except KeyError:
            return default

    def pop(self, paper_id: str, default: PaperStatusData | None = None) -> PaperStatusData | None:
        try:
            snapshot = self[paper_id]
        except KeyError:
            if default is not None:
                return default
            raise
        return snapshot


class CompatPdfPathDict(MutableMapping[str, Path]):
    """Mutable ``_pdf_paths``-shaped view backed by ``papers.pdf_path``."""

    def __init__(self, service: PaperService) -> None:
        self._service = service

    def __getitem__(self, paper_id: str) -> Path:
        pdf_path = run_async(self._service._paper_repo.get_pdf_path(paper_id))
        if pdf_path is None:
            raise KeyError(paper_id)
        return Path(pdf_path)

    def __setitem__(self, paper_id: str, path: Path) -> None:
        run_async(self._service._paper_repo.update_paths(paper_id, pdf_path=str(path)))

    def __delitem__(self, paper_id: str) -> None:
        raise NotImplementedError("pdf_path is cleared via paper delete")

    def __iter__(self) -> Iterator[str]:
        return iter(self._service._papers.keys())

    def __len__(self) -> int:
        return len(self._service._papers)

    def get(self, paper_id: str, default: Path | None = None) -> Path | None:
        try:
            return self[paper_id]
        except KeyError:
            return default


def upsert_compat_paper_detail(service: PaperService, paper_id: str, detail: PaperDetail) -> None:
    """Create or update a paper row from a legacy test ``PaperDetail`` injection."""
    existing = run_async(service._paper_repo.get(paper_id))
    pdf_path = str(Path(service._settings.upload_dir) / f"{paper_id}.pdf")
    if existing is None:
        run_async(
            service._paper_repo.create(
                paper_id,
                detail.title or paper_id,
                pdf_path,
                status=detail.status,
            ),
        )
    else:
        run_async(service._paper_repo.update_status(paper_id, status=detail.status))
    if detail.classification is not None:
        run_async(service._paper_repo.update_classification(paper_id, detail.classification))
    if detail.preview_available:
        run_async(service._paper_repo.mark_preview_available(paper_id))
    elif existing is not None and existing.preview_available and not detail.preview_available:
        run_async(
            service._paper_repo.update_paths(paper_id, graph_path=None, head_path=None),
        )
    if detail.status == PaperStatus.PENDING:
        now = detail.updated_at or detail.created_at
        run_async(
            service._pipeline_repo.save_status(
                paper_id,
                PaperStatusData(
                    paper_id=paper_id,
                    status=PaperStatus.PENDING,
                    percent=0,
                    stage=None,
                    message="test fixture",
                    updated_at=now,
                    preview_available=detail.preview_available,
                ),
            ),
        )
