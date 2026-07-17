# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""T6 contract: ingest HTTP API unchanged while benchmark baseline is script-side."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from backend.main import app
from httpx import ASGITransport, AsyncClient

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI = REPO_ROOT / "docs" / "api" / "openapi.yaml"
BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "benchmark" / "dual_rules_baseline.json"
BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "benchmark_dual_route.py"


def test_t6_baseline_fixture_tracked_in_repo() -> None:
    import json

    assert BASELINE_PATH.is_file()
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert baseline["schema_version"] == 1
    assert baseline["totals"]["dual_route_rules"] == 46


def test_t6_openapi_ingest_contract_unchanged() -> None:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    paper_status = spec["components"]["schemas"]["PaperStatusData"]["properties"]
    assert "head_refine_warnings" in paper_status
    assert "stage" in paper_status

    paper_detail = spec["components"]["schemas"]["PaperDetail"]
    detail_yaml = yaml.dump(paper_detail)
    assert "ingest_head" in detail_yaml
    assert "IngestHead" in detail_yaml


def test_t6_benchmark_script_cli_contract() -> None:
    result = subprocess.run(
        [sys.executable, str(BENCHMARK_SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0
    for flag in ("--all-corpus", "--compare-baseline", "--write-baseline", "--with-llm"):
        assert flag in result.stdout


@pytest.mark.asyncio
async def test_t6_papers_status_api_still_exposes_head_refine_fields() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/papers/hss-001/status")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["stage"] in {
            "uploading",
            "ingesting",
            "head_refining",
            "classifying",
            "extracting",
            "storing",
            "ready",
            "failed",
        }
        assert "head_refine_warnings" in data
        assert isinstance(data["head_refine_warnings"], list)
