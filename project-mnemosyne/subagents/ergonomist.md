---
name: ergonomist
description: >
  Detects structural ergonomic issues (paragraph length, sentence length,
  table overload) that increase cognitive load. Rule-based, fully deterministic.
system_prompt: system_prompts/ergonomist.system.md
input_schema: core/schemas/cognition_report.schema.json (issues section)
output_schema: core/schemas/cognition_report.schema.json (issues section)
implementation: core/scoring/ergonomist.py
mode: rule-based
---

## Invocation

```bash
python3 core/scoring/ergonomist.py --input <struct.json> --output <ergo.json>
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success — ergo.json written |
| 1 | Fatal error (bad input, unreadable file) |
| 2 | Unsupported input type |

## Severity Thresholds

| Issue Type | Trigger Condition | Severity |
|-----------|-------------------|----------|
| paragraph_too_long | word_count > 250 | high |
| paragraph_too_long | word_count 150–250 | medium |
| sentence_too_long | word_count > 35 | low |
| table_overloaded | columns > 8 or rows > 30 | medium |

## Notes

- All checks are deterministic word-count comparisons — no ML inference.
- Confidence is 0.90–0.95 for all structural rules.
- Empty documents return `{ issues: [], summary: { total: 0, by_severity: {...} } }`.
