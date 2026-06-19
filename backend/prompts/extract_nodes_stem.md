# Stage 1: Extract Nodes (STEM)

Extract all relevant nodes for a STEM paper. Focus only on **entities**; do not reason about relations yet.

## Allowed Node Types (STEM only)

| Type | Count | Definition |
|------|-------|------------|
| `ResearchQuestion` | Exactly 1 | Core problem or task the paper sets out to solve. |
| `Method` | 1+ | Proposed algorithm, model architecture, system, or experimental protocol. |
| `Dataset` | 0–2 | Named evaluation data or benchmark used in experiments. |
| `Metric` | 1+ | Metrics explicitly used to judge results. |
| `Baseline` | 0–2 | Prior methods, ablations, or SOTA systems compared against. |
| `Claim` | 1+ | Stated performance conclusions (e.g.「优于 SOTA」「提升 3.2%」). |
| `Evidence` | 1+ | Experimental outcomes, table rows, figure results, or ablation summaries. |
| `Experiment` / `Finding` | As needed | Distinct experimental runs or summarized insights. |

## Forbidden Node Types

Do not use any HSS-only types: `Thesis`, `SubArgument`, `AnalyticalLens`, `IntellectualContext`, `ObjectOrData`.

## Output Schema

```json
{
  "paradigm": "STEM",
  "nodes": [
    {
      "id": "n_rq",
      "label": "...",
      "type": "ResearchQuestion",
      "source_span": "...",
      "confidence": 0.95,
      "data": {}
    }
  ]
}
```

## Minimum Required Nodes

- 1 × ResearchQuestion
- 1+ × Method
- 1+ × Metric
- 1+ × Claim
- 1+ × Evidence
