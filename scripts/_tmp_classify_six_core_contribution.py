"""临时脚本：对 3 HSS + 3 STEM 共六篇 PDF 执行基于 core contribution 追问法的范式分类。

输出每篇的 profile、core contribution analysis、最终分类结果与置信度，
用于验证 classifier_core_contribution_enabled=true 后的三阶段分类效果。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from backend.agents.classifier_llm import (
    classify_with_llm,
    generate_profile_with_llm,
    interrogate_core_contribution_with_llm,
)
from backend.config import Settings
from backend.services.head_refine_service import refine_head_async

# Windows Git Bash 控制台默认 GBK；强制 stdout 用 UTF-8，避免打印 Unicode 字符失败。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
PAPER_IDS = ["hss-001", "hss-002", "hss-003", "stem-001", "stem-002", "stem-003"]
CORPUS_DIR = REPO_ROOT / "data" / "corpus"
OUTPUT_PATH = REPO_ROOT / "data" / "tmp-test-graphs" / "classify_six_core_contribution.json"


async def classify_one(paper_id: str, settings: Settings) -> dict:
    pdf_path = CORPUS_DIR / f"{paper_id}.pdf"
    if not pdf_path.is_file():
        return {"paper_id": paper_id, "error": "PDF not found"}

    head_result = await refine_head_async(paper_id, pdf_path, settings=settings)
    classifier_input = head_result.classifier_input

    profile = await generate_profile_with_llm(classifier_input, settings=settings)
    core = await interrogate_core_contribution_with_llm(classifier_input, settings=settings)
    classification = await classify_with_llm(
        classifier_input,
        settings=settings,
        profile=profile,
    )

    return {
        "paper_id": paper_id,
        "expected_paradigm": "HSS" if paper_id.startswith("hss") else "STEM",
        "classification": classification.paradigm.value,
        "confidence": classification.confidence,
        "reason": classification.reason,
        "profile": {
            "goal": profile.goal,
            "tools": profile.tools,
            "domain": profile.domain,
        },
        "core_contribution": {
            "summary": core.core_contribution_summary,
            "substitution_test": core.substitution_test,
            "target_journal_test": core.target_journal_test,
        },
        "classifier_input_head": classifier_input[:500] + "..." if len(classifier_input) > 500 else classifier_input,
    }


async def main() -> int:
    settings = Settings()
    print(f"CLASSIFIER_LLM_ENABLED={settings.classifier_llm_enabled}")
    print(f"CLASSIFIER_TWO_PHASE_ENABLED={settings.classifier_two_phase_enabled}")
    print(f"CLASSIFIER_CORE_CONTRIBUTION_ENABLED={settings.classifier_core_contribution_enabled}")
    print("-" * 80)

    results: list[dict] = []
    for paper_id in PAPER_IDS:
        print(f"[start] {paper_id}")
        try:
            record = await classify_one(paper_id, settings)
        except Exception as exc:
            print(f"[error] {paper_id}: {exc}")
            record = {"paper_id": paper_id, "error": str(exc)}

        results.append(record)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        print("-" * 80)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[saved] {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
