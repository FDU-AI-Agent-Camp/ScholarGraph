"""Run the BE-2 paradigm classifier on text, a file, or the V1 evaluation fixtures."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.agents import classify

LABELS_PATH = REPO_ROOT / "docs" / "v1" / "eval" / "classifier_labels.csv"
PAPERS_LIST_PATH = REPO_ROOT / "docs" / "api" / "fixtures" / "papers-list.json"


def _load_fixture_inputs() -> dict[str, str]:
    payload = json.loads(PAPERS_LIST_PATH.read_text(encoding="utf-8"))
    items = payload["data"]["items"]
    return {
        item["paper_id"]: (
            f"Title: {item['title']}\n"
            f"Known workflow status: {item['status']}"
        )
        for item in items
    }


async def _classify_text(text: str) -> dict[str, Any]:
    result = await classify(text)
    return result.model_dump(mode="json")


async def _run_eval() -> dict[str, Any]:
    inputs = _load_fixture_inputs()
    rows: list[dict[str, str]] = []
    with LABELS_PATH.open(newline="", encoding="utf-8") as labels_file:
        rows.extend(csv.DictReader(labels_file))

    results: list[dict[str, Any]] = []
    correct = 0
    for row in rows:
        paper_id = row["paper_id"]
        prediction = await classify(inputs[paper_id])
        is_correct = prediction.paradigm == row["paradigm_gold"]
        correct += int(is_correct)
        results.append(
            {
                "paper_id": paper_id,
                "gold": row["paradigm_gold"],
                "predicted": prediction.paradigm,
                "confidence": prediction.confidence,
                "correct": is_correct,
                "reason": prediction.reason,
            }
        )
    return {"accuracy": correct / len(rows), "correct": correct, "total": len(rows), "results": results}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="Classifier input text.")
    source.add_argument("--file", type=Path, help="UTF-8 text file to classify.")
    source.add_argument("--eval", action="store_true", help="Run docs/v1/eval/classifier_labels.csv evaluation.")
    return parser.parse_args()


async def _main() -> int:
    args = _parse_args()
    if args.eval:
        report = await _run_eval()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["correct"] == report["total"] else 1
    text = args.text if args.text is not None else args.file.read_text(encoding="utf-8")
    print(json.dumps(await _classify_text(text), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
