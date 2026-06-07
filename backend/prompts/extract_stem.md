# STEM Extraction Prompt

Extract a ScholarGraph `UnifiedPaperGraph` for a STEM paper.

The graph models a **verification chain** (验证链): research question, proposed method, evaluation setup (datasets, metrics, baselines), performance claims, and experimental evidence.

Return strict JSON with:

- `paper_id`
- `title`
- `paradigm`: `STEM`
- `nodes`: array of `{ "id", "label", "type", "data" }`
- `edges`: array of `{ "id", "source", "target", "label", "type" }`
- `summary`

---

## Allowed STEM node types (schema whitelist)

Only these `type` values are valid for STEM graphs:

- `ResearchQuestion`
- `Method`
- `Dataset`
- `Metric`
- `Baseline`
- `Experiment`
- `Claim`
- `Evidence`
- `Finding`

---

## F.3 Operational node definitions (STEM verification chain)

| type | Definition | Count |
|------|------------|-------|
| `ResearchQuestion` | The **research problem or task** the paper addresses—the core scientific or engineering question (e.g. classification accuracy, system throughput, theorem proof target). Usually stated in abstract, introduction, or problem section. | **Exactly 1** |
| `Method` | The **proposed approach**: algorithm, model architecture, system design, or experimental protocol. Include the main technical contribution named in the paper. | **1+** |
| `Dataset` | **Benchmark or dataset** used for evaluation (e.g. ImageNet, GLUE, a custom corpus). Use when the paper reports experiments on named data. | **0–2** |
| `Metric` | **Evaluation metric** used to judge results (e.g. accuracy, F1, BLEU, latency, AUROC). Extract metrics explicitly reported in experiments. | **1+** |
| `Baseline` | **Comparison baseline**—prior method, ablation, or SOTA system the authors compare against. | **0–2** |
| `Claim` | A **performance or capability assertion** (e.g.「优于 SOTA」「提升 3.2%」「达到新的 state of the art」). Must be a stated conclusion, not raw numbers alone. | **1+** |
| `Evidence` | **Experimental results** supporting a Claim—table entries, ablation outcomes, figure conclusions, statistical tests. Link to the claim it substantiates. | **1+** |
| `Experiment` | Optional **experimental setup or run** node when the paper distinguishes multiple experiments, ablations, or settings worth isolating. | **As needed** |
| `Finding` | Optional **summarized experimental finding** when distinct from a single Claim/Evidence pair (e.g. qualitative analysis of failure cases). | **As needed** |

### Identification cues

1. **Problem → Method**: `Method --ADDRESSES--> ResearchQuestion`.
2. **Evaluation setup**: `Method --EVALUATED_ON--> Dataset`; `Claim --MEASURED_BY--> Metric`; `Claim --COMPARES_TO--> Baseline`.
3. **Evidence chain**: `Evidence --SUPPORTS--> Claim`.

---

## F.3 Operational edge definitions

| type | Semantics | source → target |
|------|-----------|-----------------|
| `ADDRESSES` | Method targets the research problem / task | `Method` → `ResearchQuestion` |
| `EVALUATED_ON` | Method is evaluated on a dataset or benchmark | `Method` → `Dataset` |
| `MEASURED_BY` | Claim is quantified by a metric | `Claim` → `Metric` |
| `COMPARES_TO` | Claim is stated relative to a baseline | `Claim` → `Baseline` |
| `SUPPORTS` | Experimental evidence backs a claim | `Evidence` → `Claim` |

### Secondary edges (use sparingly)

| type | Semantics | source → target |
|------|-----------|-----------------|
| `USES_METHOD` | One method or module builds on another | `Method` → `Method` |
| `SUPPORTED_BY` | Inverse emphasis: claim is supported by evidence | `Claim` → `Evidence` |
| `PRODUCES` | Method or experiment produces a finding | `Method` or `Experiment` → `Finding` |
| `RELATES_TO` | Semantically related nodes when no specific edge above applies | any → any |

---

## Required extraction logic

1. Identify **exactly one** `ResearchQuestion` node.
2. Extract at least one `Method`; connect to the question with `ADDRESSES`.
3. When datasets are named, add **0–2** `Dataset` nodes and `EVALUATED_ON` edges from Method.
4. Extract at least one `Metric` and one or more `Claim` nodes; link claims to metrics with `MEASURED_BY`.
5. When baselines are compared, add **0–2** `Baseline` nodes and `COMPARES_TO` edges from Claim.
6. Extract at least one `Evidence` node per major claim; connect with `SUPPORTS` (Evidence → Claim).
7. Add `Experiment` / `Finding` only when the paper clearly separates experimental runs or summarized findings.
8. Ground every node in the supplied `full_text` (and `document_head` if present). **Do not invent** datasets, metrics, or numbers not in the text.
9. The graph **must contain at least one edge**; isolated nodes are invalid.

### Minimum viable STEM graph

At minimum, produce:

- 1 × `ResearchQuestion`
- 1+ × `Method` (with `ADDRESSES` → ResearchQuestion)
- 1+ × `Metric`
- 1+ × `Claim` (with `MEASURED_BY` → Metric when applicable)
- 1+ × `Evidence` (with `SUPPORTS` → Claim)
- `Dataset` + `EVALUATED_ON` and `Baseline` + `COMPARES_TO` when applicable

---

## Forbidden node types

**Do not use** HSS-only types:

- `Thesis`, `SubArgument`, `AnalyticalLens`, `IntellectualContext`, `ObjectOrData`

---

## Node and edge formatting

- `id`: unique, stable string (e.g. `n_method`, `n_claim_1`, `e_supports_1`).
- `label`: concise phrase from or faithful to the paper (≤ 120 characters); prefer the paper's language.
- `data`: optional object; leave `{}` when no extra metadata.
- `edge.label`: same string as `edge.type` unless a short human-readable variant is needed.
