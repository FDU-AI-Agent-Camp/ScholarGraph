#!/usr/bin/env python3
"""
单篇论文流水线一键脚本：ingest → classify → extract → store。

在仓库根目录执行（需已 uv sync）::

    uv run python scripts/run_pipeline.py --pdf data/corpus/hss-001.pdf
    uv run python scripts/run_pipeline.py --paper-id hss-001 --pdf path/to/paper.pdf --title "标题"

退出码：0 成功（ready）；1 流水线失败（failed）；2 参数/环境错误。
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from backend.config import get_settings
from backend.db.base import get_async_engine
from backend.db.bootstrap import ensure_schema
from backend.graph.workflow import run_paper_pipeline
from backend.repositories.async_bridge import run_async
from backend.repositories.paper_repository import get_paper_repository
from backend.repositories.pipeline_repository import get_pipeline_repository
from backend.schemas.paper import PaperStatus, PaperStatusData
from backend.services.paper_service import get_paper_service

EXIT_SUCCESS = 0
EXIT_PIPELINE_FAILED = 1
EXIT_USAGE_ERROR = 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="运行 ScholarGraph 单篇 PDF 建图流水线（LangGraph workflow）",
    )
    parser.add_argument(
        "--pdf",
        required=True,
        type=Path,
        help="本地 PDF 路径（相对路径相对于当前工作目录）",
    )
    parser.add_argument(
        "--paper-id",
        default=None,
        help="论文 ID；省略时自动生成 UUID",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="论文标题；省略时使用 PDF 文件名（去 .pdf）",
    )
    parser.add_argument(
        "--no-copy",
        action="store_true",
        help="不复制 PDF 到 upload_dir，直接使用给定路径（默认会复制以便与 API 上传一致）",
    )
    return parser.parse_args(argv)


async def _ensure_paper_pending(
    paper_id: str,
    *,
    title: str,
    pdf_path: str,
) -> None:
    await ensure_schema(get_async_engine())
    paper_repo = get_paper_repository()
    if await paper_repo.get(paper_id) is not None:
        return
    now = datetime.now(UTC)
    await paper_repo.create(paper_id, title, pdf_path, status=PaperStatus.PENDING)
    await get_pipeline_repository().save_status(
        paper_id,
        PaperStatusData(
            paper_id=paper_id,
            status=PaperStatus.PENDING,
            percent=0,
            stage=None,
            message="任务已创建，请轮询 status 接口",
            updated_at=now,
        ),
    )


def register_paper_for_pipeline(
    paper_id: str,
    pdf_path: Path,
    *,
    title: str | None = None,
    copy_to_upload_dir: bool = True,
) -> Path:
    """
    确保 paper_id 已登记为 pending，并将 PDF 放到 upload_dir（可选）。

    Returns:
        供 workflow 使用的 PDF 绝对路径。
    """
    resolved = pdf_path.resolve()
    if not resolved.is_file():
        msg = f"PDF 不存在: {resolved}"
        raise FileNotFoundError(msg)

    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{paper_id}.pdf"

    if copy_to_upload_dir and resolved != dest.resolve():
        shutil.copy2(resolved, dest)
        pdf_for_pipeline = str(dest)
    else:
        pdf_for_pipeline = str(resolved)

    display_title = title or resolved.stem
    run_async(_ensure_paper_pending(paper_id, title=display_title, pdf_path=pdf_for_pipeline))
    return Path(pdf_for_pipeline)


def _format_status_line(snapshot: PaperStatusData) -> str:
    stage = snapshot.stage.value if snapshot.stage is not None else "—"
    return f"[status] {snapshot.status.value} | {stage} | {snapshot.percent}% | {snapshot.message}"


async def run_single_paper_pipeline(
    paper_id: str,
    pdf_path: Path,
) -> int:
    """执行流水线并打印终态；返回进程退出码。"""
    print(f"[ScholarGraph] paper_id={paper_id}")
    print(f"[ScholarGraph] pdf={pdf_path.resolve()}")

    final = await run_paper_pipeline(paper_id, pdf_path)
    snapshot = await get_paper_service().get_status(paper_id)
    print(_format_status_line(snapshot))

    if final.get("failed") or snapshot.status == PaperStatus.FAILED:
        code = final.get("error_code", "PIPELINE_FAILED")
        detail = final.get("error_message") or snapshot.message
        print(f"[failed] {code}: {detail}", file=sys.stderr)
        return EXIT_PIPELINE_FAILED

    if snapshot.status == PaperStatus.READY:
        print("[done] 建图完成，可通过 GET /api/v1/papers/{id}/graph 查看图谱")
        return EXIT_SUCCESS

    print(f"[warn] 终态非常规: status={snapshot.status.value}", file=sys.stderr)
    return EXIT_PIPELINE_FAILED


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paper_id = args.paper_id or str(uuid4())

    try:
        pdf_for_run = register_paper_for_pipeline(
            paper_id,
            args.pdf,
            title=args.title,
            copy_to_upload_dir=not args.no_copy,
        )
    except FileNotFoundError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    return asyncio.run(run_single_paper_pipeline(paper_id, pdf_for_run))


if __name__ == "__main__":
    raise SystemExit(main())
