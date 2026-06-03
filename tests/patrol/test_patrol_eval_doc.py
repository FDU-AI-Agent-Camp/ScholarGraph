"""patrol_samples.md ↔ code constants alignment."""

from pathlib import Path

from backend.patrol.samples import CORPUS_HSS_PAPER_IDS, CORPUS_PATROL_LENSES

EVAL_DOC = Path(__file__).resolve().parents[2] / "docs" / "v1" / "eval" / "patrol_samples.md"


def test_patrol_samples_doc_exists() -> None:
    assert EVAL_DOC.is_file()


def test_patrol_samples_doc_mentions_corpus_paper_ids() -> None:
    text = EVAL_DOC.read_text(encoding="utf-8")
    for paper_id in CORPUS_HSS_PAPER_IDS:
        assert paper_id in text


def test_patrol_samples_doc_lists_eval_lens_labels() -> None:
    text = EVAL_DOC.read_text(encoding="utf-8")
    for _node_id, label in CORPUS_PATROL_LENSES.values():
        assert label in text
