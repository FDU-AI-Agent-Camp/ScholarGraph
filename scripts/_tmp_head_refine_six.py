"""临时脚本：在完整逻辑下对 3 HSS + 3 STEM 共六篇 PDF 执行 head refine。

输出每篇的 route、warnings，以及新增字段 research_object / methodology_tool /
core_intellectual_contribution 的提取结果，用于验证 INGEST_HEAD_LLM_ENABLED=true
后的完整逻辑是否生效。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Windows Git Bash 控制台默认 GBK；强制 stdout 用 UTF-8，避免打印 Unicode 字符失败。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.config import Settings
from backend.services.head_refine_service import refine_head_async

PAPER_IDS = ["hss-001", "hss-002", "hss-003", "stem-001", "stem-002", "stem-003"]
CORPUS_DIR = REPO_ROOT / "data" / "corpus"
OUTPUT_PATH = REPO_ROOT / "data" / "tmp-test-graphs" / "head_refine_six_full_logic.json"


async def main() -> int:
    settings = Settings()
    print(f"LLM_MODE={settings.llm_mode}")
    print(f"INGEST_HEAD_LLM_ENABLED={settings.ingest_head_llm_enabled}")
    print(f"INGEST_ROUTE={settings.ingest_route}")
    print("-" * 80)

    # Patch PaperService to avoid persisting head refine artifacts to data/graphs
    # during this ad-hoc evaluation script.
    with patch("backend.services.paper_service.get_paper_service") as mock_svc:
        mock_svc.return_value.apply_head_refine = MagicMock()

        results: list[dict] = []
        for paper_id in PAPER_IDS:
            pdf_path = CORPUS_DIR / f"{paper_id}.pdf"
            if not pdf_path.is_file():
                print(f"[skip] {paper_id}: PDF not found")
                continue

            print(f"[start] {paper_id}")
            try:
                result = await refine_head_async(paper_id, pdf_path, settings=settings)
            except Exception as exc:
                print(f"[error] {paper_id}: {exc}")
                results.append({"paper_id": paper_id, "error": str(exc)})
                continue

            merged = result.merged
            record = {
                "paper_id": paper_id,
                "page_count": result.page_count,
                "route": result.route.value if result.route else None,
                "warnings": result.warnings,
                "title": merged.title,
                "research_object": merged.research_object,
                "methodology_tool": merged.methodology_tool,
                "core_intellectual_contribution": merged.core_intellectual_contribution,
                "abstract_preview": merged.abstract[:200] + "..." if len(merged.abstract) > 200 else merged.abstract,
            }
            results.append(record)
            print(json.dumps(record, ensure_ascii=False, indent=2))
            print("-" * 80)

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[saved] {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
