# Stage 1: Extract Nodes (HSS)

Extract all relevant nodes for a humanities or social science paper. Focus only on **entities**; do not reason about relations yet.

## Allowed Node Types (HSS only)

| Type | Count | Definition |
|------|-------|------------|
| `Thesis` | Exactly 1 | The paper's central claim or concluding proposition. |
| `SubArgument` | 3–5 | Chapter-level supporting arguments that jointly substantiate the Thesis. |
| `AnalyticalLens` | 1+ | Theoretical framework or analytic perspective applied (name the theory/school explicitly). |
| `ObjectOrData` | 1+ | Research object, empirical material, or case examined (interviews, archives, texts, etc.). |
| `IntellectualContext` | 0–2 | Existing view, school, or tradition the author challenges, revises, or contextualizes against. |
| `Claim` | As needed | Local argumentative assertion backed by cited material. |
| `Evidence` | As needed | Supporting material or reasoning (quotations, archival facts, interview excerpts). |

## Forbidden Node Types

Do not use any STEM-only types: `ResearchQuestion`, `Method`, `Dataset`, `Metric`, `Baseline`, `Experiment`, `Finding`.

## Output Schema

```json
{
  "paradigm": "HSS",
  "nodes": [
    {
      "id": "n_thesis",
      "label": "...",
      "type": "Thesis",
      "source_span": "...",
      "confidence": 0.95,
      "data": {}
    }
  ]
}
```

## Strict Field Constraints

- `label` must be a concise academic phrase (≤ 50 characters). Do not copy full sentences.
- `source_span` must be a short textual snippet (≤ 200 characters). Quote only the relevant fragment.

⚠️ **Absolute prohibition**: Labels longer than 50 characters or direct copies of long sentences will be considered invalid output.

## Minimum Required Nodes

- 1 × Thesis
- 3–5 × SubArgument
- 1+ × AnalyticalLens
- 1+ × ObjectOrData
