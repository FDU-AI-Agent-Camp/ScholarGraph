"""Shared similarity and label-normalization helpers for patrol modes."""

from __future__ import annotations

import re

import numpy as np

_ASCII_WORD_PATTERN = re.compile(r"[a-zA-Z]+")
_ENGLISH_DOMINANCE_RATIO = 0.5


def normalize_label(label: str) -> str:
    """Normalize a node label for overlap or conflict comparison."""
    return label.strip().lower()


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity between two embedding vectors."""
    left_arr = np.asarray(left, dtype=np.float64)
    right_arr = np.asarray(right, dtype=np.float64)
    left_norm = np.linalg.norm(left_arr)
    right_norm = np.linalg.norm(right_arr)
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(left_arr @ right_arr / (left_norm * right_norm))


def cosine_similarity_matrix(
    left_vectors: list[list[float]],
    right_vectors: list[list[float]],
) -> np.ndarray:
    """Compute the cross cosine-similarity matrix between two vector sets."""
    left = np.asarray(left_vectors, dtype=np.float64)
    right = np.asarray(right_vectors, dtype=np.float64)
    left_norms = np.linalg.norm(left, axis=1, keepdims=True)
    right_norms = np.linalg.norm(right, axis=1, keepdims=True)
    left_norms[left_norms == 0] = 1.0
    right_norms[right_norms == 0] = 1.0
    left_normalized = left / left_norms
    right_normalized = right / right_norms
    return left_normalized @ right_normalized.T


def english_word_ratio(text: str) -> float:
    """Return the share of alphanumeric characters that belong to ASCII words."""
    stripped = text.strip()
    if not stripped:
        return 0.0
    ascii_chars = sum(len(word) for word in _ASCII_WORD_PATTERN.findall(stripped))
    alphanumeric_chars = sum(1 for char in stripped if char.isalnum())
    if alphanumeric_chars == 0:
        return 0.0
    return ascii_chars / alphanumeric_chars


def is_predominantly_english(text: str, *, threshold: float = _ENGLISH_DOMINANCE_RATIO) -> bool:
    """Return True when ASCII word tokens dominate the label text."""
    return english_word_ratio(text) > threshold


def derive_conflict_type(left_label: str, right_label: str) -> str:
    """Infer contradiction conflict_type from normalized thesis labels."""
    if normalize_label(left_label) == normalize_label(right_label):
        return "none"
    return "potential"


def derive_clash_aspect(left_label: str, right_label: str) -> str:
    """Infer lens clash aspect from normalized analytical-lens labels."""
    if normalize_label(left_label) == normalize_label(right_label):
        return "none"
    return "analytical_framework"
