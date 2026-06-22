# Stage 2: Build Edges (HSS)

Given the extracted nodes below, construct all meaningful edges between them. Only use node ids listed in **Available Nodes**.

## Available Nodes

{nodes_json}

## Allowed Edge Types (HSS only)

| Type | Source → Target | Semantics |
|------|-----------------|-----------|
| `SUB_ARGUMENT_OF` | SubArgument → Thesis | Sub-argument supports the central thesis. |
| `CHALLENGES` | Thesis → IntellectualContext | Thesis challenges prior scholarship. |
| `EXAMINES_THROUGH` | ObjectOrData → AnalyticalLens | Object/material is examined through a theoretical lens. |
| `LENS_OF` | AnalyticalLens → Thesis | Lens frames the overall argument. |
| `INFORMS` | AnalyticalLens → SubArgument | Lens informs a sub-argument. |
| `SUPPORTS` | Evidence → Claim or Evidence → Thesis | Evidence supports a claim or the thesis. |
| `CONTEXTUALIZES` | IntellectualContext → Thesis/SubArgument | Prior scholarship provides background. |
| `REF` | any → any | Citation or textual reference link. |

### Dynamic relation invention

If none of the predefined edge types precisely captures the relationship, **do not fall back to `RELATES_TO`**. Instead, invent a concise, specific relation verb in `SCREAMING_SNAKE_CASE` (e.g., `OPTIMIZES`, `DERIVES_FROM`, `LIMITS`, `EXTENDS`).

## Requirements

- Every SubArgument must have `SUB_ARGUMENT_OF` → Thesis.
- Every ObjectOrData should have `EXAMINES_THROUGH` → AnalyticalLens.
- Use `LENS_OF` when the lens frames the overall argument.
- Do not create edges that reference node ids not in the Available Nodes list.

## Edge Attributes

Each edge may include `rationale`, `source_span`, and `confidence`.

### CRITICAL RULE for `source_span`

You are functioning as an **exact text extractor**, not a summarizer.

- `source_span` is **required** for `SUPPORTS`, `CONTRADICTS`, and `EXPLAINS`.
- The `source_span` MUST be a **verbatim, continuous substring** copied directly from the provided chunk text.
- **DO NOT summarize. DO NOT paraphrase. DO NOT leave it empty.**
- If you construct a `SUPPORTS` or `CONTRADICTS` edge, you absolutely MUST locate the exact sentence that justifies it and copy it into `source_span`.

### `rationale` (logic path)

- `rationale` is **required** for `SUPPORTS`, `CONTRADICTS`, and `EXPLAINS`.
- Explain **why** the source relates to the target in 1–2 concrete sentences.
- Do not write tautologies like "A supports B".
- Keep it concise: Chinese ≤ 80 characters; English ≤ 30 words.

### CRITICAL: ban on generic `RELATES_TO`

- `RELATES_TO` is **strictly forbidden** unless there is genuinely no other way to express the link.
- Instead, use one of the predefined types above **or** invent a specific `SCREAMING_SNAKE_CASE` verb that captures the exact relationship.
- Good examples: `DERIVES_FROM`, `LIMITS`, `EXTENDS`, `QUALIFIES`, `REINFORCES`.

### `confidence` (quality tier)

- Optional for all edges: `"HIGH"` if explicitly stated, `"MEDIUM"` if strongly implied, `"LOW"` if speculative.

## Output Schema

```json
{
  "paradigm": "HSS",
  "edges": [
    {
      "id": "e_sub_1",
      "source": "n_sub_1",
      "target": "n_thesis",
      "label": "SUB_ARGUMENT_OF",
      "type": "SUB_ARGUMENT_OF",
      "rationale": "The sub-argument directly advances the central thesis by establishing the historical conditions of the case.",
      "source_span": "...",
      "confidence": "HIGH",
      "data": {}
    }
  ]
}
```

- You do not need to repeat the full list of available node ids in the output; only include the ``edges`` array.
