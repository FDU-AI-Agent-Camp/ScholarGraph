"""Generate two short STEM PDFs for Method Overlap + Claim Evolution demos."""

from __future__ import annotations

from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1] / "data" / "corpus"

# Content is intentionally explicit so LLM / heuristic extraction can recover:
# Method (PCA vs Principal Component Analysis), Dataset (MNIST),
# shared ResearchQuestion, and divergent Claims — matching patrol seed graphs.
PAPER_A = {
    "filename": "stem-009-PCA-on-MNIST-improves-kNN-accuracy.pdf",
    "title": "PCA on MNIST Improves k-NN Classification Accuracy",
    "authors": "Demo Author A, ScholarGraph Patrol Corpus",
    "abstract": (
        "Research Question: Does PCA improve MNIST classification accuracy? "
        "This short technical note studies whether Principal Component Analysis (PCA) "
        "improves digit recognition on the MNIST dataset. "
        "Method: PCA. Dataset: MNIST. "
        "Claim: PCA compresses MNIST features to 50 dimensions and then improves "
        "k-NN top-1 accuracy by 3% relative to the raw-pixel baseline."
    ),
    "body": [
        "1. Introduction",
        "Research Question: Does PCA improve MNIST classification accuracy?",
        "Chinese Research Question label: PCA shi fou ti sheng MNIST fen lei zhun que lu?",
        "Canonical RQ (for graph extraction): PCA 是否提升 MNIST 分类准确率？",
        "We ask whether PCA improves MNIST classification accuracy under a fixed k-NN classifier.",
        "",
        "2. Method",
        "Method: PCA",
        "We apply PCA (Principal Component Analysis) to MNIST pixel vectors before k-NN classification.",
        "Usage: Applied PCA to MNIST pixel vectors before k-NN classification.",
        "The projection retains the top 50 principal components.",
        "",
        "3. Dataset",
        "Dataset: MNIST",
        "All experiments are evaluated on the MNIST handwritten digit dataset.",
        "Training uses the standard MNIST train split; testing uses the standard MNIST test split.",
        "",
        "4. Experimental Setup",
        "Baseline: raw 784-dimensional MNIST pixels with k-NN (k=5).",
        "Proposed pipeline: PCA to 50 dimensions, then the same k-NN classifier.",
        "",
        "5. Results and Claim",
        "Claim: PCA compresses MNIST features to 50 dimensions and improves classification accuracy by 3%.",
        "Canonical Claim (for graph extraction): PCA 将 MNIST 特征压缩至 50 维后分类准确率提升 3%。",
        (
            "On MNIST, the PCA + k-NN pipeline improves top-1 accuracy by 3 percentage points "
            "over the raw-pixel k-NN baseline."
        ),
        "Therefore, under this protocol, PCA improves MNIST classification accuracy.",
        "",
        "6. Conclusion",
        "Research Question revisited: Does PCA improve MNIST classification accuracy? Yes, by 3%.",
        (
            "Key nodes for graph extraction: Method=PCA; Dataset=MNIST; "
            "ResearchQuestion=Does PCA improve MNIST classification accuracy?; "
            "Claim=PCA compresses MNIST features to 50 dimensions and improves classification accuracy by 3%."
        ),
    ],
}

PAPER_B = {
    "filename": "stem-010-Principal-Component-Analysis-MNIST-matches-baseline.pdf",
    "title": "Principal Component Analysis on MNIST Matches Baseline Accuracy",
    "authors": "Demo Author B, ScholarGraph Patrol Corpus",
    "abstract": (
        "Research Question: Does PCA improve MNIST classification accuracy? "
        "This note re-examines Principal Component Analysis for MNIST digit classification. "
        "Method: Principal Component Analysis. Dataset: MNIST. "
        "Claim: Principal Component Analysis retains 95% variance on MNIST and yields "
        "classification performance comparable to the baseline."
    ),
    "body": [
        "1. Introduction",
        "Research Question: Does PCA improve MNIST classification accuracy?",
        "Canonical RQ (for graph extraction): PCA 是否提升 MNIST 分类准确率？",
        "We revisit whether Principal Component Analysis improves MNIST classification accuracy.",
        "",
        "2. Method",
        "Method: Principal Component Analysis",
        (
            "We use Principal Component Analysis as an orthogonal basis projection that keeps "
            "the leading eigen-directions of MNIST pixel covariance."
        ),
        "Usage: Principal Component Analysis compressed MNIST features to 50 dimensions.",
        "We select the number of components that retain 95% of explained variance.",
        "",
        "3. Dataset",
        "Dataset: MNIST",
        "Evaluation is performed entirely on the MNIST dataset with the standard splits.",
        "",
        "4. Experimental Setup",
        "Baseline: raw MNIST pixels with the same downstream classifier family as prior work.",
        "Proposed pipeline: Principal Component Analysis compression, then classification.",
        "",
        "5. Results and Claim",
        (
            "Claim: Principal Component Analysis retains 95% variance on MNIST and "
            "classification performance is comparable to the baseline."
        ),
        "Canonical Claim (for graph extraction): 主成分分析在 MNIST 上保留 95% 方差，分类性能与基线相当。",
        (
            "On MNIST, Principal Component Analysis retaining 95% variance produces classification "
            "performance comparable to the baseline; we do not observe a reliable accuracy lift."
        ),
        "Therefore, under this protocol, PCA does not clearly improve MNIST classification accuracy.",
        "",
        "6. Conclusion",
        (
            "Research Question revisited: Does PCA improve MNIST classification accuracy? "
            "Not clearly; performance is comparable."
        ),
        (
            "Key nodes for graph extraction: Method=Principal Component Analysis; Dataset=MNIST; "
            "ResearchQuestion=Does PCA improve MNIST classification accuracy?; "
            "Claim=Principal Component Analysis retains 95% variance on MNIST and "
            "classification performance is comparable to the baseline."
        ),
    ],
}


def _wrap(text: str, *, fontsize: float, max_width: float) -> list[str]:
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        width = fitz.get_text_length(trial, fontname="helv", fontsize=fontsize)
        if width <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines or [""]


def write_paper(spec: dict[str, object]) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 56.0
    margin_x = 54.0
    max_width = 595.0 - 2 * margin_x

    def put(text: str, *, fontsize: float = 11.0, bold: bool = False) -> None:
        nonlocal y, page
        fontname = "hebo" if bold else "helv"
        # Strip non-latin characters for reliable Base-14 embedding; keep ASCII keys intact.
        safe = text.encode("ascii", "ignore").decode("ascii")
        if not safe.strip():
            return
        for line in _wrap(safe, fontsize=fontsize, max_width=max_width):
            if y > 790:
                page = doc.new_page(width=595, height=842)
                y = 56.0
            page.insert_text((margin_x, y), line, fontsize=fontsize, fontname=fontname)
            y += fontsize + 4
        y += 6

    put(str(spec["title"]), fontsize=16, bold=True)
    put(str(spec["authors"]), fontsize=11)
    put("Abstract", fontsize=13, bold=True)
    put(str(spec["abstract"]), fontsize=11)
    body = spec["body"]
    assert isinstance(body, list)
    for para in body:
        assert isinstance(para, str)
        if para.startswith(("1.", "2.", "3.", "4.", "5.", "6.")):
            put(para, fontsize=13, bold=True)
        elif para == "":
            y += 4
        else:
            put(para, fontsize=11)

    out = ROOT / str(spec["filename"])
    doc.save(out)
    doc.close()
    return out


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    checks = {
        "stem-009": (
            "Method: PCA",
            "Dataset: MNIST",
            "Does PCA improve MNIST classification accuracy?",
            "improves classification accuracy by 3%",
        ),
        "stem-010": (
            "Method: Principal Component Analysis",
            "Dataset: MNIST",
            "Does PCA improve MNIST classification accuracy?",
            "comparable to the baseline",
        ),
    }
    for path in (write_paper(PAPER_A), write_paper(PAPER_B)):
        text = "".join(page.get_text() for page in fitz.open(path))
        key = "stem-009" if "stem-009" in path.name else "stem-010"
        for snippet in checks[key]:
            assert snippet in text, f"missing in {path.name}: {snippet!r}"
        print(f"OK {path.name} bytes={path.stat().st_size} chars={len(text)}")
    print("text-extraction checks passed")


if __name__ == "__main__":
    main()
