"""LLM client (shared by all agent modules)."""

from backend.llm.client import LlmClient, get_llm_client

__all__ = ["LlmClient", "get_llm_client"]
