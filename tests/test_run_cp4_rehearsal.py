# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for scripts/run_cp4_rehearsal.py — SSE parse, API probes, CLI flags."""

from __future__ import annotations

import importlib.util
import sys
from unittest.mock import MagicMock, patch

import httpx
import pytest

from tests.conftest import REPO_ROOT

RUN_CP4_SCRIPT = REPO_ROOT / "scripts" / "run_cp4_rehearsal.py"


@pytest.fixture
def cp4_module():
    spec = importlib.util.spec_from_file_location("run_cp4_rehearsal", RUN_CP4_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_cp4_rehearsal"] = module
    spec.loader.exec_module(module)
    return module


def test_parse_sse_events_multiline_data(cp4_module) -> None:
    raw = (
        "event: message\n"
        'data: {"delta": "hello"}\n'
        "\n"
        "event: citation\n"
        'data: {"paper_id": "hss-001", "node_id": "n1", "label": "核心论点"}\n'
        "\n"
        "event: done\n"
        'data: {"answer_id": "ans-hss-001"}\n'
    )
    events = cp4_module.parse_sse_events(raw)
    assert [name for name, _ in events] == ["message", "citation", "done"]
    assert events[1][1]["node_id"] == "n1"


def test_report_api_checks_all_pass(cp4_module) -> None:
    mod = cp4_module
    report = mod.RehearsalReport()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/papers") and request.method == "GET":
            return httpx.Response(200, json={"data": {"items": [{"paper_id": "hss-001"}]}})
        if path.endswith("/papers/hss-001") and request.method == "GET":
            return httpx.Response(200, json={"data": {"status": "ready", "paper_id": "hss-001"}})
        if path.endswith("/papers/hss-failed-001/status"):
            return httpx.Response(
                200,
                json={"data": {"error_code": "LLM_JSON_INVALID", "status": "failed"}},
            )
        if path.endswith("/papers/hss-002/status"):
            return httpx.Response(200, json={"data": {"status": "processing", "stage": "classifying"}})
        if path.endswith("/papers/hss-001/graph"):
            return httpx.Response(200, json={"data": {"nodes": [{"id": "n1"}], "edges": []}})
        if path.endswith("/papers/hss-001/qa/stream"):
            sse = (
                "event: message\n"
                'data: {"delta": "ok"}\n\n'
                "event: citation\n"
                'data: {"paper_id": "hss-001", "node_id": "n1", "label": "核心论点"}\n\n'
                "event: done\n"
                'data: {"answer_id": "ans-hss-001"}\n\n'
            )
            return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})
        if path.endswith("/patrol"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "insights": [{"node_refs": [{"paper_id": "hss-001", "node_id": "n1", "label": "L"}]}],
                    },
                },
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    mod.report_api_checks(client, report)
    assert report.passed
    assert any(step.name == "POST /papers/hss-001/qa/stream SSE" and step.ok for step in report.steps)


def test_report_api_checks_red_qa_missing_citation(cp4_module) -> None:
    mod = cp4_module
    report = mod.RehearsalReport()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/qa/stream"):
            sse = 'event: message\ndata: {"delta": "x"}\n\nevent: done\ndata: {}\n\n'
            return httpx.Response(200, text=sse)
        if path.endswith("/papers"):
            return httpx.Response(200, json={"data": {"items": []}})
        if path.endswith("/papers/hss-001"):
            return httpx.Response(200, json={"data": {"status": "ready"}})
        if path.endswith("/papers/hss-failed-001/status"):
            return httpx.Response(200, json={"data": {"error_code": "LLM_JSON_INVALID"}})
        if path.endswith("/papers/hss-002/status"):
            return httpx.Response(200, json={"data": {"status": "processing", "stage": "x"}})
        if path.endswith("/papers/hss-001/graph"):
            return httpx.Response(200, json={"data": {"nodes": [{"id": "n1"}]}})
        if path.endswith("/patrol"):
            return httpx.Response(200, json={"data": {"insights": [{"node_refs": [{"paper_id": "a"}]}]}})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    mod.report_api_checks(client, report)
    qa_step = next(s for s in report.steps if "qa/stream" in s.name)
    assert qa_step.ok is False


def test_report_proxy_checks(cp4_module) -> None:
    mod = cp4_module
    report = mod.RehearsalReport()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"paper_id": "hss-001", "status": "ready"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    mod.report_proxy_checks(client, report)
    assert report.steps[-1].ok is True


def test_run_rehearsal_api_only_skips_frontend(cp4_module) -> None:
    mod = cp4_module
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with (
        patch.object(mod, "wait_for_url"),
        patch.object(mod.httpx, "Client", return_value=mock_client),
        patch.object(mod, "report_api_checks") as mock_api,
        patch.object(mod, "report_frontend_checks") as mock_fe,
        patch.object(mod, "report_browser_checks") as mock_browser,
    ):
        report = mod.run_rehearsal(api_only=True)

    mock_api.assert_called_once()
    mock_fe.assert_not_called()
    mock_browser.assert_not_called()
    assert report.steps[0].name == "后端就绪"


def test_run_rehearsal_skip_browser(cp4_module) -> None:
    mod = cp4_module
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with (
        patch.object(mod, "wait_for_url"),
        patch.object(mod.httpx, "Client", return_value=mock_client),
        patch.object(mod, "report_api_checks"),
        patch.object(mod, "report_frontend_checks"),
        patch.object(mod, "report_proxy_checks"),
        patch.object(mod, "report_browser_checks") as mock_browser,
    ):
        mod.run_rehearsal(skip_browser=True)

    mock_browser.assert_not_called()


def test_report_browser_checks_import_error(cp4_module, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = cp4_module
    report = mod.RehearsalReport()
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "playwright.sync_api":
            raise ImportError("no playwright")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    mod.report_browser_checks(report)
    assert report.steps[0].ok is False
    assert "playwright" in report.steps[0].detail


def test_parse_args_api_only_and_skip_browser(cp4_module) -> None:
    args = cp4_module.parse_args(["--api-only", "--skip-browser"])
    assert args.api_only is True
    assert args.skip_browser is True
