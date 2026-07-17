#!/usr/bin/env python3
# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""
从微语料 PDF 导出纯文本（BE-1）。

在仓库根目录执行::

    uv run python scripts/extract_text.py --all-corpus
    uv run python scripts/extract_text.py --paper-id stem-001
    uv run python scripts/extract_text.py --pdf data/corpus/hss-001.pdf

默认输出到与 PDF 同目录的 ``{paper_id}.txt``（已被 .gitignore 忽略）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.ingest.pdf import extract_pdf_text, resolve_paper_id

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS_DIR = REPO_ROOT / "data" / "corpus"
CORPUS_PAPER_IDS = ("stem-001", "hss-001", "hss-002")

EXIT_SUCCESS = 0
EXIT_USAGE_ERROR = 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 PDF 导出 UTF-8 纯文本")
    parser.add_argument("--pdf", type=Path, help="单个 PDF 路径")
    parser.add_argument("--paper-id", help="语料 paper_id（与 --all-corpus 互斥）")
    parser.add_argument(
        "--all-corpus",
        action="store_true",
        help=f"处理 {DEFAULT_CORPUS_DIR} 下 {', '.join(CORPUS_PAPER_IDS)}",
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=DEFAULT_CORPUS_DIR,
        help="语料目录（默认 data/corpus）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="输出目录（默认与 PDF 同目录）",
    )
    return parser.parse_args(argv)


def _resolve_jobs(args: argparse.Namespace) -> list[tuple[str, Path]]:
    if args.all_corpus:
        if args.pdf or args.paper_id:
            print("错误: --all-corpus 不能与 --pdf / --paper-id 同时使用", file=sys.stderr)
            raise SystemExit(EXIT_USAGE_ERROR)
        corpus_dir = args.corpus_dir.resolve()
        jobs: list[tuple[str, Path]] = []
        for paper_id in CORPUS_PAPER_IDS:
            pdf_path = corpus_dir / f"{paper_id}.pdf"
            if not pdf_path.is_file():
                print(f"跳过（不存在）: {pdf_path}", file=sys.stderr)
                continue
            jobs.append((paper_id, pdf_path))
        if not jobs:
            print(f"错误: {corpus_dir} 下未找到任何语料 PDF", file=sys.stderr)
            raise SystemExit(EXIT_USAGE_ERROR)
        return jobs

    if args.pdf:
        pdf_path = args.pdf.resolve()
        paper_id = resolve_paper_id(pdf_path, args.paper_id)
        return [(paper_id, pdf_path)]

    if args.paper_id:
        pdf_path = args.corpus_dir.resolve() / f"{args.paper_id}.pdf"
        return [(args.paper_id, pdf_path)]

    print("错误: 请指定 --pdf、--paper-id 或 --all-corpus", file=sys.stderr)
    raise SystemExit(EXIT_USAGE_ERROR)


def export_one(paper_id: str, pdf_path: Path, *, output_dir: Path | None) -> Path:
    text = extract_pdf_text(pdf_path)
    target_dir = output_dir.resolve() if output_dir else pdf_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / f"{paper_id}.txt"
    out_path.write_text(text, encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    jobs = _resolve_jobs(args)

    for paper_id, pdf_path in jobs:
        if not pdf_path.is_file():
            print(f"错误: PDF 不存在: {pdf_path}", file=sys.stderr)
            return EXIT_USAGE_ERROR
        try:
            out_path = export_one(paper_id, pdf_path, output_dir=args.output_dir)
        except (FileNotFoundError, ValueError) as exc:
            print(f"错误 [{paper_id}]: {exc}", file=sys.stderr)
            return EXIT_USAGE_ERROR
        char_count = len(out_path.read_text(encoding="utf-8"))
        print(f"[ok] {paper_id}: {pdf_path.name} -> {out_path} ({char_count} chars)")

    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
