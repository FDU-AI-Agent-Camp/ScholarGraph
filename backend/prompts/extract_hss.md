# HSS Extraction Prompt

Extract a ScholarGraph `UnifiedPaperGraph` for a humanities or social science paper.

Return strict JSON with:

- `paper_id`
- `title`
- `paradigm`: `HSS`
- `nodes`: array of `{ "id", "label", "type", "data" }`
- `edges`: array of `{ "id", "source", "target", "label", "type" }`
- `summary`

Allowed HSS node types:

- `Thesis`
- `SubArgument`
- `AnalyticalLens`
- `IntellectualContext`
- `ObjectOrData`
- `Claim`
- `Evidence`

Required logic:

- Identify the paper's central thesis.
- Extract 3 to 5 major sub-arguments and connect each with `SUB_ARGUMENT_OF` to the thesis.
- Identify the author's analytical lens or theory and the object/material being examined.
- Connect object/material to theory with `EXAMINES_THROUGH`.
- Identify the existing view, school, or literature the author challenges, revises, or contextualizes.
- Do not use STEM-only node types such as `Metric`, `Baseline`, or `Dataset`.

