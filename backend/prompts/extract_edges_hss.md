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
| `RELATES_TO` | any → any | Generic semantic relation when no specific type applies. |
| `REF` | any → any | Citation or textual reference link. |

## Requirements

- Every SubArgument must have `SUB_ARGUMENT_OF` → Thesis.
- Every ObjectOrData should have `EXAMINES_THROUGH` → AnalyticalLens.
- Use `LENS_OF` when the lens frames the overall argument.
- Do not create edges that reference node ids not in the Available Nodes list.

## Output Schema

```json
{
  "paradigm": "HSS",
  "node_ids": ["n_thesis", "n_sub_1", ...],
  "edges": [
    {
      "id": "e_sub_1",
      "source": "n_sub_1",
      "target": "n_thesis",
      "label": "SUB_ARGUMENT_OF",
      "type": "SUB_ARGUMENT_OF",
      "source_span": "...",
      "data": {}
    }
  ]
}
```
