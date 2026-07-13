"""Tests for patrol RAG degradation summary helper."""

from backend.patrol.rag_service import RAG_DEGRADED_META_KEY, append_rag_degradation_notice


def test_append_rag_degradation_notice_index_not_ready() -> None:
    summary = "两篇论文方法重叠分析完成。"
    meta = {RAG_DEGRADED_META_KEY: {"paper_ids": ["stem-001"], "reason": "index_not_ready"}}
    result = append_rag_degradation_notice(summary, meta)
    assert "向量索引尚未就绪" in result
    assert "stem-001" in result


def test_append_rag_degradation_notice_no_meta_unchanged() -> None:
    summary = "无降级。"
    assert append_rag_degradation_notice(summary, {}) == summary


def test_append_rag_degradation_notice_idempotent() -> None:
    meta = {RAG_DEGRADED_META_KEY: {"paper_ids": ["stem-001"], "reason": "index_not_ready"}}
    summary = append_rag_degradation_notice("完成。", meta)
    assert append_rag_degradation_notice(summary, meta) == summary
