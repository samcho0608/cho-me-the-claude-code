---
name: ontologist
description: >
  Detects forward concept references in technical documents.
  Produces a ConceptGraph JSON with confidence-scored findings.
system_prompt: system_prompts/ontologist.system.md
input_schema: core/schemas/concept_graph.schema.json
output_schema: core/schemas/concept_graph.schema.json
implementation: core/scoring/concept_graph.py
mode: rule-based
---

## Invocation

```bash
python3 core/scoring/concept_graph.py --input <struct.json> --output <cg.json>
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success — cg.json written |
| 1 | Fatal error (bad input, unreadable file) |
| 2 | Unsupported input type |

## Notes

- Confidence < 0.40 findings appear in `warnings[]` only.
- Empty documents produce valid output with empty arrays.
- Does not require network access.
