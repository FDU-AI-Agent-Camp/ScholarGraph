# STEM Extraction Prompt

Extract a ScholarGraph `UnifiedPaperGraph` for a STEM paper.

Return strict JSON with:

- `paper_id`
- `title`
- `paradigm`: `STEM`
- `nodes`: array of `{ "id", "label", "type", "data" }`
- `edges`: array of `{ "id", "source", "target", "label", "type" }`
- `summary`

Allowed STEM node types:

- `ResearchQuestion`
- `Method`
- `Dataset`
- `Metric`
- `Baseline`
- `Experiment`
- `Claim`
- `Evidence`
- `Finding`

Required logic:

- Identify the research problem or task.
- Identify the proposed method or system.
- Identify datasets/benchmarks, metrics, baselines, claims, and supporting evidence.
- Link method to problem with `ADDRESSES`.
- Link method to dataset with `EVALUATED_ON`.
- Link claims to metrics/baselines and evidence with `MEASURED_BY`, `COMPARES_TO`, and `SUPPORTS`.
- Do not use HSS-only node types such as `AnalyticalLens`, `IntellectualContext`, or `ObjectOrData`.

