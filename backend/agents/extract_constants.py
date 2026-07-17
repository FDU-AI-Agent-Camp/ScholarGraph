# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Shared constants for graph extraction (Phase F)."""

# Generic fallback code (kept for backward compatibility)
EXTRACT_HEURISTIC_FALLBACK_CODE = "extract_heuristic_fallback"
EXTRACT_HEURISTIC_FALLBACK_MESSAGE = "触发启发式Fallback!"

# MVP preview notification
MVP_SKELETON_PREVIEW_CODE = "mvp_skeleton_preview"
MVP_SKELETON_PREVIEW_MESSAGE = "当前为 MVP 宏观骨架图谱，深度节点仍在后台组装中。"

# Fine-grained fallback / degrade machine codes surfaced in extract_warnings.
EXTRACT_LLM_TIMEOUT_CODE = "extract_llm_timeout"
EXTRACT_LLM_TIMEOUT_MESSAGE = "LLM 调用超时，已降级为启发式Fallback。"

EXTRACT_LLM_RATE_LIMITED_CODE = "extract_llm_rate_limited"
EXTRACT_LLM_RATE_LIMITED_MESSAGE = "LLM 触发限流，已降级为启发式Fallback。"

EXTRACT_LLM_JSON_INVALID_CODE = "extract_llm_json_invalid"
EXTRACT_LLM_JSON_INVALID_MESSAGE = "LLM 返回非合法 JSON，已降级为启发式Fallback。"

EXTRACT_SCHEMA_VALIDATION_FAILED_CODE = "extract_schema_validation_failed"
EXTRACT_SCHEMA_VALIDATION_FAILED_MESSAGE = "Schema 校验失败，已降级为启发式Fallback。"

EXTRACT_CONTEXT_WINDOW_EXCEEDED_CODE = "extract_context_window_exceeded"
EXTRACT_CONTEXT_WINDOW_EXCEEDED_MESSAGE = "上下文窗口超限，已降级为启发式Fallback。"

# Quality gate warning: graph passed extraction but confidence is too low.
LOW_CONFIDENCE_GRAPH_CODE = "low_confidence_graph"
LOW_CONFIDENCE_GRAPH_MESSAGE = "图谱质量未达置信门控，建议人工复核或重新抽取。"
