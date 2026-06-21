# STEM Extraction Prompt

Extract a ScholarGraph `UnifiedPaperGraph` for a STEM paper.

The graph models a **verification chain** (验证链): research question, proposed method, evaluation setup (datasets, metrics, baselines), performance claims, and experimental evidence.

Return strict JSON with:

- `paper_id`
- `title`
- `paradigm`: `STEM`
- `nodes`: array of `{ "id", "label", "type", "source_span", "confidence", "data" }`
- `edges`: array of `{ "id", "source", "target", "label", "type", "rationale", "source_span", "confidence", "data" }`
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
| `ResearchQuestion` | 研究问题 / 任务定义 — the core problem or task the paper sets out to solve (e.g. image classification, property prediction, system latency). Usually in abstract, introduction, or task section. | **Exactly 1** |
| `Method` | 方法、模型、系统 — the proposed algorithm, model architecture, system, or experimental protocol that constitutes the technical contribution. | **1+** |
| `Dataset` | 数据集 / benchmark — named evaluation data (e.g. ImageNet, GLUE, MoleculeNet). Add only when the paper reports experiments on specific data. | **0–2** |
| `Metric` | 评测指标 — metrics used to judge results (e.g. accuracy, F1, BLEU, AUROC, RMSE). Extract only metrics explicitly used in experiments. | **1+** |
| `Baseline` | 对比基线 — prior methods, ablations, or SOTA systems compared against (e.g. BERT, ResNet-50, vanilla GNN). | **0–2** |
| `Claim` | 性能声称（优于 SOTA 等）— stated performance conclusions (e.g.「优于 SOTA」「提升 3.2%」「达到新的 state of the art」), not raw table cells alone. | **1+** |
| `Evidence` | 实验结果、表格结论 — experimental outcomes, table rows, figure results, or ablation summaries that substantiate a Claim. | **1+** |
| `Experiment` / `Finding` | 可选细化 — use `Experiment` for distinct experimental runs/settings; use `Finding` for summarized insights beyond a single Claim/Evidence pair. | **As needed** |

### Identification cues

1. **Problem → Method**: `Method --ADDRESSES--> ResearchQuestion`.
2. **Evaluation setup**: `Method --EVALUATED_ON--> Dataset`; `Claim --MEASURED_BY--> Metric`; `Claim --COMPARES_TO--> Baseline`.
3. **Evidence chain**: `Evidence --SUPPORTS--> Claim`.

---

## F.3 Operational edge definitions

| type | Semantics | source → target |
|------|-----------|-----------------|
| `ADDRESSES` | 方法针对问题 — method addresses the research question / task | `Method` → `ResearchQuestion` |
| `EVALUATED_ON` | 方法在某数据上评测 — method is evaluated on a dataset or benchmark | `Method` → `Dataset` |
| `MEASURED_BY` | 声称由某指标度量 — claim is quantified by a metric | `Claim` → `Metric` |
| `COMPARES_TO` | 声称与基线对比 — claim is stated relative to a baseline | `Claim` → `Baseline` |
| `SUPPORTS` | 实验支撑声称 — experimental evidence backs a claim | `Evidence` → `Claim` |

### Secondary edges (use sparingly)

| type | Semantics | source → target |
|------|-----------|-----------------|
| `USES_METHOD` | One method or module builds on another | `Method` → `Method` |
| `PRODUCES` | Method or experiment produces a finding | `Method` or `Experiment` → `Finding` |
| `RELATES_TO` | Semantically related nodes when no specific edge above applies | any → any |

### Forbidden edge directions

- **Do not use `SUPPORTED_BY` or any inverse of `SUPPORTS`**. All evidence-to-claim relations must be expressed as `Evidence --SUPPORTS--> Claim` only.

---

## Edge attribute requirements

Edges may carry three additional fields: `rationale`, `source_span`, and `confidence`.

### `rationale` (logic path)

- **Required** for core argument edges: `SUPPORTS`, `CONTRADICTS`, `EXPLAINS`.
- **Optional** for all other edge types.
- Must explain **why** the source relates to the target in 1–2 sentences.
- Must contain concrete logical evidence. Do **not** write tautologies like "A supports B".
- Chinese ≤ 80 characters; English ≤ 30 words.

### CRITICAL RULE for `source_span`

You are functioning as an **exact text extractor**, not a summarizer.

- **Required** for `SUPPORTS`, `CONTRADICTS`, and `EXPLAINS`.
- MUST be a **verbatim, continuous substring** copied directly from the paper text.
- **DO NOT summarize. DO NOT paraphrase. DO NOT leave it empty.**
- For every `SUPPORTS` or `CONTRADICTS` edge, locate the exact sentence that justifies it and copy it into `source_span`.

### `confidence` (quality tier)

- Optional for all edges.
- Use `"HIGH"` when the relation is explicitly stated in the text.
- Use `"MEDIUM"` when the relation is strongly implied.
- Use `"LOW"` when the relation is speculative or inferred.

### Example

```json
{
  "id": "e_supports_1",
  "source": "n_evidence_1",
  "target": "n_claim_1",
  "label": "SUPPORTS",
  "type": "SUPPORTS",
  "rationale": "The 86.33% accuracy metric directly quantifies the model's performance, supporting the claim that it outperforms baselines.",
  "source_span": "The knowledge graph-enhanced DeepSeek-V3 model achieved the best performance... with an accuracy rate of 86.33%",
  "confidence": "HIGH",
  "data": {}
}
```

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
