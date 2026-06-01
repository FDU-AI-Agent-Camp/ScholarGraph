#!/usr/bin/env python3
"""
CP4 端到端联调 / rehearsal 脚本。

在仓库根目录、前后端已启动时执行::

    uv run python scripts/run_cp4_rehearsal.py

可选::

    uv run python scripts/run_cp4_rehearsal.py --seed
    uv run python scripts/run_cp4_rehearsal.py --api-only          # C-05 后端 API
    uv run python scripts/run_cp4_rehearsal.py --skip-browser      # C-05 + C-06，无 Playwright
    uv run python scripts/run_cp4_rehearsal.py --frontend-only

退出码：0 全部通过；1 有失败步骤。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

BACKEND_BASE = "http://127.0.0.1:8000"
FRONTEND_BASE = "http://127.0.0.1:5173"
API_PREFIX = "/api/v1"
WAIT_TIMEOUT_SECONDS = 60
POLL_INTERVAL_SECONDS = 0.5


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class RehearsalReport:
    steps: list[StepResult] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.steps.append(StepResult(name=name, ok=ok, detail=detail))
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"[{mark}] {name}{suffix}")

    @property
    def passed(self) -> bool:
        return all(step.ok for step in self.steps)


def wait_for_url(client: httpx.Client, url: str, label: str) -> None:
    deadline = time.monotonic() + WAIT_TIMEOUT_SECONDS
    last_error = ""
    while time.monotonic() < deadline:
        try:
            response = client.get(url, timeout=5.0)
            if response.status_code < 500:
                return
            last_error = f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(POLL_INTERVAL_SECONDS)
    msg = f"{label} 未在 {WAIT_TIMEOUT_SECONDS}s 内就绪: {url} ({last_error})"
    raise TimeoutError(msg)


def parse_sse_events(raw: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    event_name = "message"
    data_lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())
        elif line == "" and data_lines:
            payload = json.loads("\n".join(data_lines))
            events.append((event_name, payload))
            event_name = "message"
            data_lines = []
    if data_lines:
        payload = json.loads("\n".join(data_lines))
        events.append((event_name, payload))
    return events


def run_seed() -> None:
    import subprocess
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    seed_cmds = [
        [sys.executable, str(repo_root / "scripts" / "run_patrol.py"), "--seed-demo-graphs"],
        # hss-001 恢复为 M2 graph-hss，供 GET graph + QA SSE 探针
        [sys.executable, str(repo_root / "scripts" / "run_qa.py"), "--seed-demo-graph"],
    ]
    for cmd in seed_cmds:
        print(">>", " ".join(cmd))
        completed = subprocess.run(cmd, cwd=repo_root, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"seed 失败: {' '.join(cmd)} → 退出码 {completed.returncode}")


def run_rehearsal(
    *,
    frontend_only: bool = False,
    api_only: bool = False,
    skip_browser: bool = False,
) -> RehearsalReport:
    report = RehearsalReport()

    with httpx.Client(follow_redirects=True) as client:
        try:
            wait_for_url(client, f"{BACKEND_BASE}/docs", "后端")
            report.add("后端就绪", True, BACKEND_BASE)
        except TimeoutError as exc:
            report.add("后端就绪", False, str(exc))
            return report

        if not frontend_only:
            report_api_checks(client, report)

        if api_only:
            return report

        try:
            wait_for_url(client, FRONTEND_BASE, "前端")
            report.add("前端就绪", True, FRONTEND_BASE)
        except TimeoutError as exc:
            report.add("前端就绪", False, str(exc))
            return report

        report_frontend_checks(client, report)
        report_proxy_checks(client, report)

    if not skip_browser:
        report_browser_checks(report)

    return report


def report_api_checks(client: httpx.Client, report: RehearsalReport) -> None:
    api = f"{BACKEND_BASE}{API_PREFIX}"

    list_resp = client.get(f"{api}/papers")
    list_ok = list_resp.status_code == 200
    list_body = list_resp.json() if list_ok else {}
    items = list_body.get("data", {}).get("items", [])
    report.add(
        "GET /papers 列表",
        list_ok and isinstance(items, list),
        f"{len(items)} items" if list_ok else list_resp.text[:120],
    )

    ready_resp = client.get(f"{api}/papers/hss-001")
    ready_data = ready_resp.json().get("data", {}) if ready_resp.status_code == 200 else {}
    report.add(
        "GET /papers/hss-001 详情 ready",
        ready_resp.status_code == 200 and ready_data.get("status") == "ready",
        str(ready_data.get("status", ready_resp.status_code)),
    )

    failed_resp = client.get(f"{api}/papers/hss-failed-001/status")
    failed_data = failed_resp.json().get("data", {}) if failed_resp.status_code == 200 else {}
    report.add(
        "GET /papers/hss-failed-001/status 失败态",
        failed_data.get("error_code") == "LLM_JSON_INVALID",
        str(failed_data.get("error_code")),
    )

    processing_resp = client.get(f"{api}/papers/hss-002/status")
    processing_data = processing_resp.json().get("data", {}) if processing_resp.status_code == 200 else {}
    report.add(
        "GET /papers/hss-002/status processing",
        processing_data.get("status") == "processing",
        str(processing_data.get("stage")),
    )

    graph_resp = client.get(f"{api}/papers/hss-001/graph")
    graph_data = graph_resp.json().get("data", {}) if graph_resp.status_code == 200 else {}
    node_count = len(graph_data.get("nodes", []))
    report.add(
        "GET /papers/hss-001/graph 图谱",
        graph_resp.status_code == 200 and node_count > 0,
        f"{node_count} nodes",
    )

    qa_resp = client.post(
        f"{api}/papers/hss-001/qa/stream",
        json={"question": "CP4 rehearsal: 核心论点是什么？"},
        headers={"Accept": "text/event-stream"},
        timeout=30.0,
    )
    qa_events = parse_sse_events(qa_resp.text) if qa_resp.status_code == 200 else []
    event_names = [name for name, _ in qa_events]
    citation_ok = any(name == "citation" for name in event_names)
    report.add(
        "POST /papers/hss-001/qa/stream SSE",
        qa_resp.status_code == 200 and "message" in event_names and citation_ok and "done" in event_names,
        ",".join(event_names) or qa_resp.text[:120],
    )

    patrol_resp = client.post(
        f"{api}/patrol",
        json={"paper_ids": ["hss-001", "hss-002"], "mode": "lens_clash"},
        timeout=60.0,
    )
    patrol_data = patrol_resp.json().get("data", {}) if patrol_resp.status_code == 200 else {}
    insight_count = len(patrol_data.get("insights", []))
    node_ref_count = len(patrol_data.get("insights", [{}])[0].get("node_refs", [])) if insight_count else 0
    report.add(
        "POST /patrol lens_clash",
        patrol_resp.status_code == 200 and insight_count > 0 and node_ref_count > 0,
        f"{insight_count} insights, {node_ref_count} node_refs",
    )


def report_frontend_checks(client: httpx.Client, report: RehearsalReport) -> None:
    """SPA shell smoke — rendered content verified separately via Playwright."""
    pages: list[tuple[str, str]] = [
        ("工作台 Home", "/"),
        ("文献库 Papers", "/papers"),
        ("详情 ready", "/papers/hss-001"),
        ("详情 failed", "/papers/hss-failed-001"),
        ("图谱 Graph", "/papers/hss-001/graph"),
        ("巡检 Patrol", "/patrol"),
    ]
    for label, path in pages:
        resp = client.get(f"{FRONTEND_BASE}{path}", timeout=30.0)
        html = resp.text
        shell_ok = resp.status_code == 200 and 'id="app"' in html and "ScholarGraph" in html
        report.add(
            f"前端 SPA 壳 {label}",
            shell_ok,
            path,
        )


def report_browser_checks(report: RehearsalReport) -> None:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError:
        report.add(
            "浏览器渲染检查",
            False,
            "未安装 playwright（uv sync --group e2e && uv run playwright install chromium）",
        )
        return

    browser_pages: list[tuple[str, str, list[str]]] = [
        ("工作台 Home", "/", ["文献库", "共同体巡检"]),
        ("文献库 Papers", "/papers", ["文献库"]),
        ("详情 ready", "/papers/hss-001", ["hss-001"]),
        ("详情 failed", "/papers/hss-failed-001", ["LLM_JSON_INVALID"]),
        ("图谱 Graph", "/papers/hss-001/graph", ["知识图谱"]),
        ("巡检 Patrol", "/patrol", ["共同体巡检", "运行巡检"]),
    ]

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            report.add(
                "浏览器渲染检查",
                False,
                f"Chromium 未安装: {exc}（uv run playwright install chromium）",
            )
            return

        page = browser.new_page()
        try:
            for label, path, needles in browser_pages:
                url = f"{FRONTEND_BASE}{path}"
                try:
                    page.goto(url, wait_until="networkidle", timeout=30_000)
                    body_text = page.locator("body").inner_text(timeout=10_000)
                    missing = [needle for needle in needles if needle not in body_text]
                    report.add(
                        f"浏览器页面 {label}",
                        not missing,
                        f"missing={missing}" if missing else url,
                    )
                except PlaywrightTimeout as exc:
                    report.add(f"浏览器页面 {label}", False, str(exc))

            page.goto(f"{FRONTEND_BASE}/papers/hss-001", wait_until="networkidle", timeout=30_000)
            qa_input = page.locator("textarea").first
            qa_input.fill("CP4 rehearsal：核心论点？")
            page.get_by_role("button", name="提问").click()
            page.wait_for_timeout(2000)
            body_text = page.locator("body").inner_text()
            qa_ok = (
                "引用节点" in body_text
                or "核心论点" in body_text
                or "Mock 答复" in body_text
                or "尚未接入" in body_text
            )
            report.add("浏览器 QA SSE 流式", qa_ok, "详情页问答区")

            page.goto(f"{FRONTEND_BASE}/patrol", wait_until="networkidle", timeout=30_000)
            page.locator(".patrol-view__run").click()
            page.wait_for_timeout(5000)
            patrol_text = page.locator("body").inner_text()
            patrol_ok = any(
                needle in patrol_text
                for needle in (
                    "理论视角",
                    "Lens",
                    "分子考古",
                    "政治传播",
                    "Mock 巡检",
                    "巡检摘要",
                )
            )
            report.add("浏览器 Patrol 运行", patrol_ok, "/patrol")
        finally:
            browser.close()


def report_proxy_checks(client: httpx.Client, report: RehearsalReport) -> None:
    proxy_url = f"{FRONTEND_BASE}{API_PREFIX}/papers/hss-001/status"
    resp = client.get(proxy_url, timeout=15.0)
    data = resp.json().get("data", {}) if resp.status_code == 200 else {}
    report.add(
        "Vite 代理 /api/v1 → 后端",
        resp.status_code == 200 and data.get("paper_id") == "hss-001",
        proxy_url,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ScholarGraph CP4 联调 rehearsal")
    parser.add_argument("--seed", action="store_true", help="运行前 seed patrol + M2 QA 评测图谱")
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="仅直连后端 API 探针（C-05，无需前端）",
    )
    parser.add_argument(
        "--skip-browser",
        action="store_true",
        help="跳过 Playwright 浏览器步（C-05 + C-06 SPA/代理）",
    )
    parser.add_argument(
        "--frontend-only",
        action="store_true",
        help="跳过直连后端 API 检查（仅页面 + 代理）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print("=" * 60)
    print("ScholarGraph CP4 Rehearsal")
    print("=" * 60)

    if args.seed:
        run_seed()

    report = run_rehearsal(
        frontend_only=args.frontend_only,
        api_only=args.api_only,
        skip_browser=args.skip_browser,
    )

    print()
    print("=" * 60)
    passed = sum(1 for step in report.steps if step.ok)
    total = len(report.steps)
    print(f"结果: {passed}/{total} 通过")
    if not report.passed:
        print("失败步骤:")
        for step in report.steps:
            if not step.ok:
                print(f"  - {step.name}: {step.detail}")
    print("=" * 60)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
