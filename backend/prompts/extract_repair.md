# Repair Previous Extraction Output

Your previous extraction produced invalid output. The validation errors are listed below.

## Validation Errors

{error_messages}

## Previous Attempt

{previous_json}

## Instructions

1. Fix all validation errors listed above.
2. Do not change correct content unnecessarily.
3. Ensure all ids are unique.
4. Ensure all edge `source` and `target` values reference existing node ids.
5. Ensure all node types are from the allowed whitelist for {paradigm}.
6. Edge types should preferably be from the allowed list below. If none fits, you may invent a specific, concise verb in `SCREAMING_SNAKE_CASE` (e.g., `OPTIMIZES`, `DERIVES_FROM`).
7. **Do not lazily use `RELATES_TO`** unless there is genuinely no other way to express the link.
8. Return the corrected JSON in the same schema.

## Allowed Node Types

{allowed_node_types}

## Preferred Edge Types

{allowed_edge_types}
