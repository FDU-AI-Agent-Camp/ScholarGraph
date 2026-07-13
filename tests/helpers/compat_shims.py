"""Test-only dict-like shims for legacy ``service._papers`` / ``_status`` assignments (D8)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, MutableMapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from backend.api.exceptions import ApiError
from backend.repositories import run_async
from backend.schemas.paper import PaperDetail, PaperStatus, PaperStatusData, PipelineStage

if TYPE_CHECKING:
    from backend.services.paper_service import PaperService

_COMPAT_POP_MISSING: Any = object()

COMPAT_PAPER_ID_PAGE_SIZE = 200


class CompatPaperDict(MutableMapping[str, PaperDetail]):
    """Mutable ``_papers``-shaped view backed by ``PaperRepository`` (tests only)."""

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
        upsert_compat_paper_detail(self._service, paper_id, detail)

    def __delitem__(self, paper_id: str) -> None:
        if not run_async(self._service._paper_repo.delete(paper_id)):
            raise KeyError(paper_id)

    def __iter__(self) -> Iterator[str]:
        offset = 0
        while True:
            items, total = run_async(
                self._service._paper_repo.list(offset=offset, limit=COMPAT_PAPER_ID_PAGE_SIZE),
            )
            if not items:
                break
            for paper in items:
                yield paper.paper_id
            offset += COMPAT_PAPER_ID_PAGE_SIZE
            if offset >= total:
                break

    def __len__(self) -> int:
        _, total = run_async(self._service._paper_repo.list(limit=0))
        return total

    def get(self, paper_id: str, default: PaperDetail | None = None) -> PaperDetail | None:
        try:
            return self[paper_id]
        except KeyError:
            return default

    def pop(
        self,
        paper_id: str,
        default: PaperDetail | None = _COMPAT_POP_MISSING,
    ) -> PaperDetail | None:
        try:
            detail = self[paper_id]
        except KeyError:
            if default is not _COMPAT_POP_MISSING:
                return default
            raise
        del self[paper_id]
        return detail

    def keys(self) -> Iterable[str]:
        return list(self)


class CompatStatusDict(MutableMapping[str, PaperStatusData]):
    """Mutable ``_status``-shaped view backed by ``PipelineRepository`` (tests only)."""

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
        if not run_async(self._service._pipeline_repo.delete_run(paper_id)):
            raise KeyError(paper_id)

    def __iter__(self) -> Iterator[str]:
        return iter(self._service._papers.keys())

    def __len__(self) -> int:
        return len(self._service._papers)

    def get(self, paper_id: str, default: PaperStatusData | None = None) -> PaperStatusData | None:
        try:
            return self[paper_id]
        except KeyError:
            return default

    def pop(
        self,
        paper_id: str,
        default: PaperStatusData | None = _COMPAT_POP_MISSING,
    ) -> PaperStatusData | None:
        try:
            snapshot = self[paper_id]
        except KeyError:
            if default is not _COMPAT_POP_MISSING:
                return default
            raise
        del self[paper_id]
        return snapshot


class CompatPdfPathDict(MutableMapping[str, Path]):
    """Mutable ``_pdf_paths``-shaped view backed by ``papers.pdf_path`` (tests only)."""

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
        if run_async(self._service._paper_repo.get(paper_id)) is None:
            raise KeyError(paper_id)
        default_pdf = str(Path(self._service._settings.upload_dir) / f"{paper_id}.pdf")
        run_async(self._service._paper_repo.update_paths(paper_id, pdf_path=default_pdf))

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
    now = detail.updated_at or detail.created_at
    if now is None:
        from datetime import UTC, datetime

        now = datetime.now(UTC)
    if detail.status in (PaperStatus.READY, PaperStatus.READY_WITH_WARNINGS):
        snapshot = PaperStatusData(
            paper_id=paper_id,
            status=detail.status,
            percent=100,
            stage=PipelineStage.READY,
            message="test fixture",
            updated_at=now,
            preview_available=detail.preview_available,
        )
    elif detail.status == PaperStatus.PROCESSING:
        snapshot = PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.PROCESSING,
            percent=50,
            stage=PipelineStage.CLASSIFYING,
            message="test fixture",
            updated_at=now,
            preview_available=detail.preview_available,
        )
    elif detail.status == PaperStatus.PENDING:
        snapshot = PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.PENDING,
            percent=0,
            stage=None,
            message="test fixture",
            updated_at=now,
            preview_available=detail.preview_available,
        )
    else:
        snapshot = PaperStatusData(
            paper_id=paper_id,
            status=detail.status,
            percent=0,
            stage=PipelineStage.FAILED,
            message="test fixture",
            updated_at=now,
            preview_available=detail.preview_available,
        )
    run_async(service._pipeline_repo.save_status(paper_id, snapshot))


def attach_paper_service_compat_shims(service: PaperService) -> None:
    """Mount legacy dict shims on a ``PaperService`` instance (pytest only)."""
    service._papers = CompatPaperDict(service)  # type: ignore[attr-defined]
    service._status = CompatStatusDict(service)  # type: ignore[attr-defined]
    service._pdf_paths = CompatPdfPathDict(service)  # type: ignore[attr-defined]


def detach_paper_service_compat_shims(service: PaperService) -> None:
    """Remove test shims so production-shaped instances stay clean."""
    for attr in ("_papers", "_status", "_pdf_paths"):
        if hasattr(service, attr):
            delattr(service, attr)
