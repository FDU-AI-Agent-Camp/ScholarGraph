"""Tests for Patrol configuration advisories (claim_evolution RQ funnel)."""

from __future__ import annotations

from backend.config import Settings


class TestPatrolClaimRqFunnelConfig:
    def test_funnel_enabled_requires_reranker_and_model(self) -> None:
        disabled = Settings(_env_file=None, reranker_enabled=False, reranker_model="bge-reranker-v2-m3")
        assert disabled.patrol_claim_rq_funnel_enabled() is False

        missing_model = Settings(_env_file=None, reranker_enabled=True, reranker_model="")
        assert missing_model.patrol_claim_rq_funnel_enabled() is False

        ready = Settings(_env_file=None, reranker_enabled=True, reranker_model="bge-reranker-v2-m3")
        assert ready.patrol_claim_rq_funnel_enabled() is True

    def test_patrol_config_warnings_live_reranker_disabled(self) -> None:
        settings = Settings(
            _env_file=None,
            llm_mode="live",
            reranker_enabled=False,
            patrol_claim_rq_coarse_threshold=0.42,
            patrol_claim_rq_rerank_threshold=0.60,
            patrol_claim_rq_threshold=0.75,
            patrol_claim_rq_threshold_english=0.55,
        )
        warnings = settings.patrol_config_warnings()
        assert len(warnings) == 1
        assert "RERANKER_ENABLED=false" in warnings[0]
        assert "0.42" in warnings[0]
        assert "0.75" in warnings[0]

    def test_patrol_config_warnings_live_reranker_missing_model(self) -> None:
        settings = Settings(_env_file=None, llm_mode="live", reranker_enabled=True, reranker_model="")
        warnings = settings.patrol_config_warnings()
        assert len(warnings) == 1
        assert "RERANKER_MODEL" in warnings[0]

    def test_patrol_config_warnings_mock_returns_empty(self) -> None:
        settings = Settings(_env_file=None, llm_mode="mock", reranker_enabled=False)
        assert settings.patrol_config_warnings() == []

    def test_patrol_config_warnings_live_funnel_ready_is_empty(self) -> None:
        settings = Settings(
            _env_file=None,
            llm_mode="live",
            reranker_enabled=True,
            reranker_model="bge-reranker-v2-m3",
        )
        assert settings.patrol_config_warnings() == []
