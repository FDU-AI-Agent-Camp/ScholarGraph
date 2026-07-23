# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""PaperService bind / get / reset composition-root wiring."""

from __future__ import annotations

from backend.services.paper_service import PaperService, bind_paper_service, get_paper_service, reset_paper_service


def test_bind_get_reset_paper_service_round_trip() -> None:
    reset_paper_service()
    custom = PaperService()
    bind_paper_service(custom)
    assert get_paper_service() is custom
    reset_paper_service()
    assert get_paper_service() is not custom


def test_get_paper_service_cache_clear_alias_resets_singleton() -> None:
    first = get_paper_service()
    get_paper_service.cache_clear()
    second = get_paper_service()
    assert second is not first
