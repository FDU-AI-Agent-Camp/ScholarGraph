"""Minimal connectivity probe for the configured cloud reranker.

Usage (from repository root):
    uv run python scripts/test_reranker.py

The script loads ``backend/config.py`` settings and runs two small probes:

1. ``connectivity`` – send a mixed set of documents to verify the service is
   reachable and returns sensible relative rankings.

2. ``synonym`` – send several paraphrases of the same concept to verify the
   reranker assigns high scores when the query and document are semantically
   equivalent.  This is the regime the semantic-clustering merge gate cares
   about.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from backend.config import get_settings


@dataclass(frozen=True)
class RerankCase:
    query: str
    documents: list[str]
    label: str


def _build_url(base_url: str | None) -> str:
    """Append ``/rerank`` to the configured base URL."""
    if not base_url:
        msg = "缺少 Reranker API 基地址：请在 .env 中设置 RERANKER_API_BASE_URL 或 LLM_API_BASE_URL"
        raise ValueError(msg)
    base = base_url.rstrip("/")
    if base.endswith("/rerank"):
        return base
    return f"{base}/rerank"


def _call_reranker(
    *,
    model: str,
    query: str,
    documents: list[str],
    api_base_url: str,
    api_key: str,
    top_n: int | None = None,
) -> dict[str, Any]:
    """POST a rerank request and return the parsed JSON response."""
    if not model:
        msg = "缺少 Reranker 模型名：请在 .env 中设置 RERANKER_MODEL"
        raise ValueError(msg)
    if not api_key:
        msg = "缺少 Reranker API Key：请在 .env 中设置 RERANKER_API_KEY 或 SCHOLARGRAPH_API_KEY"
        raise ValueError(msg)

    payload: dict[str, Any] = {
        "model": model,
        "query": query,
        "documents": documents,
    }
    if top_n is not None:
        payload["top_n"] = top_n

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    url = _build_url(api_base_url)
    print(f"POST {url}")
    print(f"model={model!r}, documents={len(documents)}")

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


def _extract_scores(raw: dict[str, Any], num_docs: int) -> list[dict[str, Any]]:
    """Normalize reranker response into a list of {index, score} dicts."""
    results = raw.get("results")
    if results is None:
        results = raw.get("data", [])

    normalized: list[dict[str, Any]] = []
    for item in results:
        if isinstance(item, dict):
            index = item.get("index")
            score = item.get("relevance_score") or item.get("score")
            normalized.append({"index": index, "score": score})

    if not normalized and "scores" in raw:
        normalized = [
            {"index": i, "score": score}
            for i, score in enumerate(raw["scores"])
            if i < num_docs
        ]

    return sorted(normalized, key=lambda x: x["score"] or 0.0, reverse=True)


def _print_case(case: RerankCase, raw: dict[str, Any], threshold: float) -> None:
    print(f"\n=== {case.label} ===")
    print(f"query: {case.query}")
    print("\n原始响应:")
    print(json.dumps(raw, ensure_ascii=False, indent=2))

    scores = _extract_scores(raw, len(case.documents))
    print("\n归一化得分（按相关性降序）:")
    for entry in scores:
        idx = entry["index"]
        score = entry["score"]
        doc = case.documents[idx] if idx is not None and 0 <= idx < len(case.documents) else "N/A"
        print(f"  score={score:.4f}  doc[{idx}]: {doc}")

    above = [s for s in scores if s["score"] is not None and s["score"] >= threshold]
    print(f"\n阈值 {threshold} 以上共 {len(above)} 条")


def _run_case(settings, case: RerankCase) -> dict[str, Any]:
    return _call_reranker(
        model=settings.reranker_model,
        query=case.query,
        documents=case.documents,
        api_base_url=settings.reranker_api_base_url_effective,
        api_key=settings.reranker_api_key_effective,
        top_n=len(case.documents),
    )


def main() -> None:
    settings = get_settings()

    if not settings.reranker_enabled:
        print("RERANKER_ENABLED=false，跳过重排序服务测试。")
        print("如需测试，请在 .env 中设置 RERANKER_ENABLED=true 并填写 RERANKER_MODEL。")
        return

    cases = [
        RerankCase(
            label="connectivity",
            query="Y-chromosome haplogroup diversification in Sherpas",
            documents=[
                "Sherpa Y-chromosome lineages show close affinity with Tibetan populations.",
                "The paper studies mitochondrial DNA rather than Y-chromosome markers.",
                "PCA reveals three major paternal haplogroups dominating the Sherpa gene pool.",
                "Climate change impacts alpine vegetation distribution in the Himalayas.",
                "Haplogroup D-M174 and O-M175 account for the majority of Sherpa paternal ancestry.",
            ],
        ),
        RerankCase(
            label="synonym",
            query="PCA was used to visualize population genetic structure",
            documents=[
                "Principal component analysis visualizes population genetic structure.",
                "We applied PCA to explore population structure.",
                "Principal components analysis was performed to examine genetic clustering.",
                "Climate change impacts alpine vegetation distribution in the Himalayas.",
                "Mitochondrial DNA was sequenced to trace maternal ancestry.",
            ],
        ),
    ]

    for case in cases:
        try:
            raw = _run_case(settings, case)
        except httpx.HTTPStatusError as exc:
            print(f"HTTP 错误: {exc.response.status_code}")
            print(exc.response.text)
            raise
        _print_case(case, raw, settings.reranker_threshold)


if __name__ == "__main__":
    main()
