"""Tests for model-aware semantic clustering thresholds."""

from __future__ import annotations

from backend.config import DEFAULT_EMBEDDING_MODEL_THRESHOLDS, Settings


class TestSemanticThresholdDefaults:
    def test_bge_m3_defaults(self) -> None:
        settings = Settings(
            _env_file=None,
            semantic_similarity_threshold=-1.0,
            semantic_knn_threshold=-1.0,
            embedding_model="bge-m3",
        )
        assert settings.semantic_similarity_threshold_effective == 0.85
        assert settings.semantic_knn_threshold_effective == 0.75

    def test_openai_text_embedding_3_small_defaults(self) -> None:
        settings = Settings(
            _env_file=None,
            semantic_similarity_threshold=-1.0,
            semantic_knn_threshold=-1.0,
            embedding_model="text-embedding-3-small",
        )
        assert settings.semantic_similarity_threshold_effective == 0.65
        assert settings.semantic_knn_threshold_effective == 0.55

    def test_unknown_model_falls_back_to_default(self) -> None:
        settings = Settings(
            _env_file=None,
            semantic_similarity_threshold=-1.0,
            semantic_knn_threshold=-1.0,
            embedding_model="some-unknown-model",
        )
        assert (
            settings.semantic_similarity_threshold_effective
            == DEFAULT_EMBEDDING_MODEL_THRESHOLDS["default"]["similarity"]
        )
        assert settings.semantic_knn_threshold_effective == DEFAULT_EMBEDDING_MODEL_THRESHOLDS["default"]["knn"]

    def test_explicit_env_threshold_overrides_model_default(self) -> None:
        settings = Settings(
            _env_file=None,
            semantic_similarity_threshold=0.92,
            semantic_knn_threshold=0.88,
            embedding_model="bge-m3",
        )
        assert settings.semantic_similarity_threshold_effective == 0.92
        assert settings.semantic_knn_threshold_effective == 0.88

    def test_patrol_claim_rq_threshold_english_default(self) -> None:
        settings = Settings(
            _env_file=None,
            patrol_claim_rq_threshold=0.75,
            patrol_claim_rq_threshold_english=0.55,
        )
        assert settings.patrol_claim_rq_threshold_effective("PCA 是否提升分类准确率？") == 0.75
        assert settings.patrol_claim_rq_threshold_effective("Does PCA improve classification accuracy?") == 0.55
