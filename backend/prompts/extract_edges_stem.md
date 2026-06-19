# Stage 2: Build Edges (STEM)

Given the extracted nodes below, construct all meaningful edges between them. Only use node ids listed in **Available Nodes**.

## Available Nodes

{nodes_json}

## Allowed Edge Types (STEM only)

| Type | Source → Target | Semantics |
|------|-----------------|-----------|
| `ADDRESSES` | Method → ResearchQuestion | Method addresses the research question. |
| `USES_METHOD` | Method → Method | One method or module builds on another. |
| `EVALUATED_ON` | Method → Dataset | Method is evaluated on a dataset or benchmark. |
| `MEASURED_BY` | Claim → Metric | Claim is quantified by a metric. |
| `COMPARES_TO` | Claim → Baseline | Claim is stated relative to a baseline. |
| `SUPPORTS` | Evidence → Claim | Experimental evidence backs a claim. |
| `SUPPORTED_BY` | Claim → Evidence | Inverse emphasis (claim supported by evidence). |
| `PRODUCES` | Method/Experiment → Finding | Method or experiment produces a finding. |
| `RELATES_TO` | any → any | Generic semantic relation when no specific type applies. |

## Requirements

- The ResearchQuestion must have at least one Method connected via `ADDRESSES`.
- Each major Claim must have at least one Evidence connected via `SUPPORTS`.
- Claims linked to Metrics/Baselines must use `MEASURED_BY` / `COMPARES_TO`.
- Do not create edges that reference node ids not in the Available Nodes list.

## Output Schema

```json
{
  "paradigm": "STEM",
  "node_ids": ["n_rq", "n_method", ...],
  "edges": [
    {
      "id": "e_method_rq",
      "source": "n_method",
      "target": "n_rq",
      "label": "ADDRESSES",
      "type": "ADDRESSES",
      "source_span": "...",
      "data": {}
    }
  ]
}
```
