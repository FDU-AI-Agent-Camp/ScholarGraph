# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Architecture contracts for first-class delete and re-extract services."""

from __future__ import annotations

from backend.repositories.paper_repository import PaperRepository
from backend.repositories.pipeline_repository import PipelineRepository
from backend.services.paper_delete_service import PaperDeleteService
from backend.services.paper_pipeline_ops import PaperPipelineOpsService
from backend.services.reextract_service import ReextractService


def test_delete_service_owns_direct_dependencies() -> None:
    paper_repo = PaperRepository()
    pipeline_ops = PaperPipelineOpsService(PipelineRepository())

    service = PaperDeleteService(paper_repo=paper_repo, pipeline_ops=pipeline_ops)

    assert service._paper_repository is paper_repo
    assert service._pipeline_ops is pipeline_ops


def test_reextract_service_owns_direct_dependencies() -> None:
    paper_repo = PaperRepository()
    pipeline_ops = PaperPipelineOpsService(PipelineRepository())

    service = ReextractService(paper_repo=paper_repo, pipeline_ops=pipeline_ops)

    assert service._paper_repository is paper_repo
    assert service._pipeline_ops is pipeline_ops
