# HSS Extraction Prompt

Extract a ScholarGraph `UnifiedPaperGraph` for a humanities or social science paper.

The graph models an **argumentation tree** (论证树): central thesis, chapter-level sub-arguments, theoretical lens, qualitative materials, and the intellectual tradition the author engages with.

Return strict JSON with:

- `paper_id`
- `title`
- `paradigm`: `HSS`
- `nodes`: array of `{ "id", "label", "type", "data" }`
- `edges`: array of `{ "id", "source", "target", "label", "type" }`
- `summary`

---

## Allowed HSS node types (schema whitelist)

Only these `type` values are valid for HSS graphs:

- `Thesis`
- `SubArgument`
- `AnalyticalLens`
- `IntellectualContext`
- `ObjectOrData`
- `Claim`
- `Evidence`

---

## F.3 Operational node definitions (HSS argumentation tree)

| type | Definition | Count |
|------|------------|-------|
| `Thesis` | The paper's **central claim** or concluding proposition—the main thing the author wants the reader to accept. Usually appears in the abstract, introduction conclusion, or final section (phrases like「本文认为」「本文主张」「we argue that」). | **Exactly 1** |
| `SubArgument` | **Chapter-level supporting arguments** that jointly substantiate the Thesis. Each should be a distinct argumentative move (not a mere section title). Derive from major headings,「首先/其次/再次」, or core paragraphs that advance the main claim. | **3–5** |
| `AnalyticalLens` | The **theoretical framework or analytic perspective** the author applies (e.g. historical institutionalism, public sphere theory, structural holes, feminist critique, postcolonial lens). Name the theory or school explicitly when the text does. | **1+** |
| `ObjectOrData` | The **research object, empirical material, or case** examined—interviews, archives, field sites, texts, policy documents, datasets in qualitative sense, etc. Be specific (e.g.「某村落宗族访谈」「晚清通商口岸档案」). | **1+** |
| `IntellectualContext` | An **existing view, school, scholar, or literature tradition** that the author **challenges, revises, or contextualizes against**. Look in the introduction / literature review for contrast markers (「然而」「既有研究认为…但」「过去的研究忽略了」). Omit if the paper does not clearly position against prior work. | **0–2** |
| `Claim` | A **local argumentative assertion** within the evidence chain (optional). Use when the text states a sub-claim that is explicitly backed by cited material or analysis—not when it is already captured as Thesis or SubArgument. | **As needed** |
| `Evidence` | **Supporting material or reasoning** for a Claim or Thesis (optional)—quotations, archival facts, interview excerpts, comparative analysis, etc. Use only when an explicit evidence chain is visible in the text. | **As needed** |

### Identification cues

1. **IntellectualContext**: Author names a tradition they oppose or refine; create `Thesis --CHALLENGES--> IntellectualContext`.
2. **SubArgument chain**: Map each major supporting line to `SubArgument --SUB_ARGUMENT_OF--> Thesis`.
3. **Lens vs material**: Map `ObjectOrData --EXAMINES_THROUGH--> AnalyticalLens`; link lens to thesis/arguments with `LENS_OF` / `INFORMS`.

---

## F.3 Operational edge definitions

| type | Semantics | source → target |
|------|-----------|-----------------|
| `SUB_ARGUMENT_OF` | 分论点支撑核心论点 — sub-argument supports the central thesis | `SubArgument` → `Thesis` |
| `CHALLENGES` | 本文论点挑战既有解释 — this paper's thesis challenges existing scholarship | `Thesis` → `IntellectualContext` |
| `EXAMINES_THROUGH` | 以某理论审视对象/材料 — object or material is examined through a theoretical lens | `ObjectOrData` → `AnalyticalLens` |
| `LENS_OF` | 理论视角作用于核心论点 — analytical lens frames the central thesis | `AnalyticalLens` → `Thesis` |
| `INFORMS` | 理论视角支撑分论点 — analytical lens informs a sub-argument | `AnalyticalLens` → `SubArgument` |
| `SUPPORTS` | 证据支撑主张 — evidence supports a claim or the thesis | `Evidence` → `Claim` or `Evidence` → `Thesis` |

### Secondary edges (use sparingly)

| type | Semantics | source → target |
|------|-----------|-----------------|
| `CONTEXTUALIZES` | Prior scholarship provides background without direct challenge | `IntellectualContext` → `Thesis` or `SubArgument` |
| `RELATES_TO` | Semantically related nodes when no specific edge above applies | any → any |
| `REF` | Citation or textual reference link between nodes | any → any |

---

## Required extraction logic

1. Identify **exactly one** `Thesis` node from the paper's core conclusion.
2. Extract **3 to 5** `SubArgument` nodes; connect each to the Thesis with `SUB_ARGUMENT_OF`.
3. Extract at least one `AnalyticalLens` and one `ObjectOrData`; connect with `EXAMINES_THROUGH`.
4. Connect `AnalyticalLens` to `Thesis` with `LENS_OF` when the lens frames the overall argument; use `INFORMS` for lens → sub-argument links.
5. When the author clearly critiques prior work, add **0–2** `IntellectualContext` nodes and `CHALLENGES` edges from Thesis.
6. Add `Claim` / `Evidence` nodes and `SUPPORTS` edges **only** when the text presents an explicit local evidence chain.
7. Ground every node in the supplied `full_text` (and `document_head` if present). **Do not invent** scholars, theories, or materials not supported by the text.
8. The graph **must contain at least one edge**; isolated nodes are invalid.

### Minimum viable HSS graph

At minimum, produce:

- 1 × `Thesis`
- 3–5 × `SubArgument` (each with `SUB_ARGUMENT_OF` → Thesis)
- 1+ × `AnalyticalLens`
- 1+ × `ObjectOrData` (with `EXAMINES_THROUGH` → lens)
- `IntellectualContext` + `CHALLENGES` when applicable

---

## Forbidden node types

**Do not use** STEM-only types:

- `ResearchQuestion`, `Method`, `Dataset`, `Metric`, `Baseline`, `Experiment`, `Finding`

---

## Node and edge formatting

- `id`: unique, stable string (e.g. `n_thesis`, `n_sub_1`, `e_sub_1`).
- `label`: concise phrase from or faithful to the paper (≤ 120 characters); prefer the paper's language.
- `data`: optional object; leave `{}` when no extra metadata.
- `edge.label`: same string as `edge.type` unless a short human-readable variant is needed.
