"""Deterministic heuristic guardrails for QA benchmark (Dual-Track Track A)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

# Numeric literals in required_patterns, e.g. "0.89", "92%", "-1.5"
_PATTERN_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?%?$")

# Percent tokens in free text, e.g. "15%", "0.89 %"
_EXTRACT_PERCENT_RE = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*%")

# Plain numeric tokens (decimals/integers without trailing %)
_EXTRACT_PLAIN_NUMBER_RE = re.compile(r"(?<![\w.])(-?\d+\.\d+)(?![\w.])|(?<![\w.])(-?\d+)(?![\w.%])")

# Dataset / benchmark identifiers (STEM): ImageNet, CIFAR-10, MNIST, GLUE, etc.
_DATASET_TOKEN_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*\b")

_DEFAULT_ABS_TOLERANCE = 1e-9
_DEFAULT_RELATIVE_TOLERANCE = 0.01
_MIN_GOLDEN_REFERENCE_CHARS = 1


def _resolve_numeric_abs_tol(gold: dict[str, Any]) -> float:
    """Resolve gold-level absolute tolerance (``numeric_abs_tol`` preferred over legacy ``numeric_tolerance``)."""
    if "numeric_abs_tol" in gold:
        return float(gold["numeric_abs_tol"])
    if "numeric_tolerance" in gold:
        return float(gold["numeric_tolerance"])
    return _DEFAULT_ABS_TOLERANCE


def _resolve_numeric_rel_tol(gold: dict[str, Any]) -> float:
    """Resolve gold-level relative tolerance."""
    return float(gold.get("numeric_rel_tol", _DEFAULT_RELATIVE_TOLERANCE))


@dataclass(frozen=True, slots=True)
class NumericExpectation:
    """One expected numeric value with optional absolute/relative tolerance."""

    value: float
    abs_tol: float = _DEFAULT_ABS_TOLERANCE
    rel_tol: float = _DEFAULT_RELATIVE_TOLERANCE


@dataclass
class HeuristicGuardrailResult:
    """Outcome of deterministic guardrail checks before / alongside LLM Judge."""

    passed_required_patterns: bool
    has_forbidden_patterns: bool
    forbidden_tripped: bool
    numeric_match: bool
    dataset_match: bool
    graph_element_recall: float
    extracted_numbers: list[float] = field(default_factory=list)
    expected_numbers: list[float] = field(default_factory=list)
    missing_numbers: list[float] = field(default_factory=list)
    extracted_datasets: list[str] = field(default_factory=list)
    expected_datasets: list[str] = field(default_factory=list)
    missing_datasets: list[str] = field(default_factory=list)
    verbosity_rate: float = 0.0
    paradigm_aligned: bool = True
    golden_reference_length: int = 0
    answer_char_length: int = 0
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "passed_required_patterns": self.passed_required_patterns,
            "has_forbidden_patterns": self.has_forbidden_patterns,
            "forbidden_tripped": self.forbidden_tripped,
            "numeric_match": self.numeric_match,
            "dataset_match": self.dataset_match,
            "graph_element_recall": round(self.graph_element_recall, 4),
            "verbosity_rate": round(self.verbosity_rate, 4),
            "paradigm_aligned": self.paradigm_aligned,
            "golden_reference_length": self.golden_reference_length,
            "answer_char_length": self.answer_char_length,
            "extracted_numbers": self.extracted_numbers,
            "expected_numbers": self.expected_numbers,
            "missing_numbers": self.missing_numbers,
            "extracted_datasets": self.extracted_datasets,
            "expected_datasets": self.expected_datasets,
            "missing_datasets": self.missing_datasets,
        }


def is_heuristic_hard_fuse_tripped(guardrails: HeuristicGuardrailResult) -> bool:
    """Track A hard fuse for dual-track OR: forbidden, numeric, or dataset gate failure."""
    if guardrails.forbidden_tripped:
        return True
    if guardrails.expected_numbers and not guardrails.numeric_match:
        return True
    if guardrails.expected_datasets and not guardrails.dataset_match:
        return True
    return False


def _parse_numeric_expectations(gold: dict[str, Any]) -> list[NumericExpectation]:
    """Resolve expected numbers from explicit gold fields or required_patterns."""
    raw = gold.get("expected_numbers")
    default_abs_tol = _resolve_numeric_abs_tol(gold)
    default_rel_tol = _resolve_numeric_rel_tol(gold)
    if isinstance(raw, list) and raw:
        expectations: list[NumericExpectation] = []
        for item in raw:
            if isinstance(item, dict):
                value = _normalize_gold_numeric(str(item["value"]))
                abs_tol = float(item.get("abs_tol", item.get("tolerance", default_abs_tol)))
                rel_tol = float(item.get("rel_tol", default_rel_tol))
                expectations.append(NumericExpectation(value=value, abs_tol=abs_tol, rel_tol=rel_tol))
            else:
                expectations.append(
                    NumericExpectation(
                        value=_normalize_gold_numeric(str(item)),
                        abs_tol=default_abs_tol,
                        rel_tol=default_rel_tol,
                    ),
                )
        return expectations

    expectations = []
    for pattern in gold.get("required_patterns", []):
        text = str(pattern).strip()
        if _PATTERN_NUMBER_RE.match(text):
            expectations.append(
                NumericExpectation(
                    value=_normalize_gold_numeric(text),
                    abs_tol=default_abs_tol,
                    rel_tol=default_rel_tol,
                ),
            )
    return expectations


def _normalize_gold_numeric(token: str) -> float:
    """Normalize gold numeric tokens; ``15%`` → ``0.15``."""
    text = token.strip()
    if text.endswith("%"):
        return float(text[:-1].strip()) / 100.0
    return float(text)


def _resolve_expected_datasets(gold: dict[str, Any]) -> list[str]:
    explicit = gold.get("expected_datasets")
    if isinstance(explicit, list) and explicit:
        return [str(name).strip() for name in explicit if str(name).strip()]

    datasets: list[str] = []
    for pattern in gold.get("required_patterns", []):
        text = str(pattern).strip()
        if _PATTERN_NUMBER_RE.match(text):
            continue
        if _DATASET_TOKEN_RE.fullmatch(text):
            datasets.append(text)
    return datasets


def extract_numbers_from_text(text: str) -> list[float]:
    """Pull numeric literals from answer text, normalizing percentages to decimals."""
    numbers: list[float] = []
    percent_spans: list[tuple[int, int]] = []

    for match in _EXTRACT_PERCENT_RE.finditer(text):
        numbers.append(float(match.group(1)) / 100.0)
        percent_spans.append(match.span())

    def _inside_percent_span(start: int, end: int) -> bool:
        return any(p_start <= start and end <= p_end for p_start, p_end in percent_spans)

    for match in _EXTRACT_PLAIN_NUMBER_RE.finditer(text):
        if _inside_percent_span(match.start(), match.end()):
            continue
        token = match.group(0)
        try:
            numbers.append(float(token))
        except ValueError:
            continue
    return numbers


def numeric_values_match(
    expected: float,
    candidate: float,
    *,
    abs_tol: float = _DEFAULT_ABS_TOLERANCE,
    rel_tol: float = _DEFAULT_RELATIVE_TOLERANCE,
) -> bool:
    """STEM numeric equivalence via ``math.isclose(rel_tol=..., abs_tol=...)`` dual gate.

    Effective window: ``|a-b| <= max(rel_tol * max(|a|,|b|), abs_tol)``.
    Configure per-gold ``numeric_rel_tol`` / ``numeric_abs_tol`` instead of tightening global defaults.
    """
    return math.isclose(candidate, expected, rel_tol=rel_tol, abs_tol=abs_tol)


def extract_datasets_from_text(text: str) -> list[str]:
    """Pull dataset-like tokens from answer text."""
    return [match.group(0) for match in _DATASET_TOKEN_RE.finditer(text)]


def _numbers_satisfied(
    expected: list[NumericExpectation],
    found: list[float],
) -> tuple[bool, list[float], list[float]]:
    if not expected:
        return True, [], []

    missing: list[float] = []
    matched: list[float] = []
    for spec in expected:
        hit = next(
            (
                value
                for value in found
                if numeric_values_match(
                    spec.value,
                    value,
                    abs_tol=spec.abs_tol,
                    rel_tol=spec.rel_tol,
                )
            ),
            None,
        )
        if hit is None:
            missing.append(spec.value)
        else:
            matched.append(hit)
    return not missing, matched, missing


def _datasets_satisfied(expected: list[str], answer_text: str, extracted: list[str]) -> tuple[bool, list[str]]:
    if not expected:
        return True, []

    answer_lower = answer_text.lower()
    extracted_lower = {token.lower() for token in extracted}
    missing: list[str] = []
    for name in expected:
        name_lower = name.lower()
        if name_lower not in answer_lower and name_lower not in extracted_lower:
            missing.append(name)
    return not missing, missing


def compute_graph_element_recall(
    citations: list[dict[str, Any]],
    gold: dict[str, Any],
) -> float:
    cited_node_ids = {c.get("node_id", "") for c in citations if c.get("type") in (None, "node")}
    cited_edge_ids = {c.get("edge_id", "") for c in citations if c.get("type") == "edge"}
    expected_nodes = set(gold.get("nodes", []))
    expected_edges = set(gold.get("edges", []))

    node_recall = len(cited_node_ids & expected_nodes) / max(len(expected_nodes), 1)
    edge_recall = len(cited_edge_ids & expected_edges) / max(len(expected_edges), 1)
    if (len(expected_nodes) + len(expected_edges)) == 0:
        return 1.0
    return (node_recall + edge_recall) / max(len(expected_nodes) + len(expected_edges), 1) * 2


def derive_golden_reference_text(gold: dict[str, Any]) -> str:
    """Build a minimal golden answer footprint for verbosity comparison.

    Prefer explicit ``reference_answer``; otherwise join ``required_patterns``
    as a proxy for the shortest acceptable response length.
    """
    explicit = gold.get("reference_answer")
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()

    patterns = [str(pattern).strip() for pattern in gold.get("required_patterns", []) if str(pattern).strip()]
    return " ".join(patterns)


def compute_verbosity_rate(answer_text: str, gold: dict[str, Any]) -> float:
    """Character inflation heuristic: ``max(0, 1 - len(gold) / len(answer))``.

    When the model answer is ~3× the golden reference length, rate ≈ 0.67.
    """
    model_len = len(answer_text.strip())
    if model_len == 0:
        return 0.0

    golden_len = len(derive_golden_reference_text(gold))
    if golden_len < _MIN_GOLDEN_REFERENCE_CHARS:
        return 0.0

    return max(0.0, 1.0 - golden_len / model_len)


def compute_paradigm_aligned(
    paradigm: str | None,
    *,
    passed_required_patterns: bool,
    has_forbidden_patterns: bool,
    numeric_match: bool,
    dataset_match: bool,
    numeric_expectations: list[NumericExpectation],
    expected_datasets: list[str],
) -> bool:
    """Deterministic paradigm gate beyond forbidden-pattern fuse."""
    if has_forbidden_patterns:
        return False

    normalized = (paradigm or "").strip().upper()
    if normalized == "STEM":
        has_stem_expectations = bool(numeric_expectations) or bool(expected_datasets)
        if has_stem_expectations:
            return passed_required_patterns and numeric_match and dataset_match
        return passed_required_patterns

    if normalized == "HSS":
        return passed_required_patterns

    return passed_required_patterns and not has_forbidden_patterns


def run_heuristic_guardrails(
    answer_text: str,
    citations: list[dict[str, Any]],
    gold: dict[str, Any],
    *,
    paradigm: str | None = None,
) -> HeuristicGuardrailResult:
    """Run Track A: forbidden fuse, pattern gates, numeric/dataset extraction checks."""
    answer_lower = answer_text.lower()

    passed_required = all(str(pattern).lower() in answer_lower for pattern in gold.get("required_patterns", []))
    forbidden_hits = [
        str(pattern) for pattern in gold.get("forbidden_patterns", []) if str(pattern).lower() in answer_lower
    ]
    has_forbidden = bool(forbidden_hits)
    forbidden_tripped = has_forbidden

    numeric_specs = _parse_numeric_expectations(gold)
    extracted_numbers = extract_numbers_from_text(answer_text)
    numeric_ok, _, missing_numbers = _numbers_satisfied(numeric_specs, extracted_numbers)

    expected_datasets = _resolve_expected_datasets(gold)
    extracted_datasets = extract_datasets_from_text(answer_text)
    dataset_ok, missing_datasets = _datasets_satisfied(expected_datasets, answer_text, extracted_datasets)

    graph_recall = compute_graph_element_recall(citations, gold)

    golden_reference = derive_golden_reference_text(gold)
    answer_char_length = len(answer_text.strip())
    verbosity_rate = compute_verbosity_rate(answer_text, gold)
    paradigm_aligned = compute_paradigm_aligned(
        paradigm,
        passed_required_patterns=passed_required,
        has_forbidden_patterns=has_forbidden,
        numeric_match=numeric_ok,
        dataset_match=dataset_ok,
        numeric_expectations=numeric_specs,
        expected_datasets=expected_datasets,
    )

    passed = not forbidden_tripped and passed_required and numeric_ok and dataset_ok and paradigm_aligned

    return HeuristicGuardrailResult(
        passed_required_patterns=passed_required,
        has_forbidden_patterns=has_forbidden,
        forbidden_tripped=forbidden_tripped,
        numeric_match=numeric_ok,
        dataset_match=dataset_ok,
        graph_element_recall=graph_recall,
        extracted_numbers=extracted_numbers,
        expected_numbers=[spec.value for spec in numeric_specs],
        missing_numbers=missing_numbers,
        extracted_datasets=extracted_datasets,
        expected_datasets=expected_datasets,
        missing_datasets=missing_datasets,
        verbosity_rate=verbosity_rate,
        paradigm_aligned=paradigm_aligned,
        golden_reference_length=len(golden_reference),
        answer_char_length=answer_char_length,
        passed=passed,
    )
