---
name: refactor
description: Apply safe cognitive-load-reducing transformations to a document based on a Mnemosyne analysis report. Splits oversized paragraphs, inserts forward-reference previews, and writes a refactor log. Use when asked to "refactor", "rewrite", "reduce friction", or "fix the document" after an analysis.
---

# Mnemosyne: Refactor

Applies safe, reviewer-approved structural transformations to a document based on a `cognition_report.json` produced by `/mnemosyne:analyze`.

## Usage

```
/mnemosyne:refactor --report <path> [--output-dir <dir>] [--moderate] [--high-risk]
```

**Arguments:**
- `--report <path>` — path to `cognition_report.json` (required)
- `--output-dir <dir>` — output directory (default: `./output/`)
- `--moderate` — also apply sentence-splitting transforms
- `--high-risk` — also attempt table restructuring (experimental)

## What It Does

```bash
cd project-mnemosyne
npx ts-node commands/refactor.ts --report {{ARGUMENTS}}
```

The refactor command:
1. **Validates** the report via `report_validator.py` — checks source hash, staleness, and mode consistency
2. **Applies safe transforms** (always):
   - Split paragraphs > 150 words at sentence boundaries
   - Insert forward-reference preview callouts above first use of undefined terms
3. **Applies moderate transforms** (with `--moderate`):
   - Break sentences > 35 words
4. **Applies high-risk transforms** (with `--high-risk`):
   - Attempt table restructuring (experimental, may require manual review)

## Output

| File | Contents |
|------|----------|
| `output/refactored/<filename>` | Transformed document (original extension preserved) |
| `output/refactor_plan.md` | Human-readable list of all transforms applied and skipped |
| `output/refactor_log.json` | Machine-readable log (schema: `core/schemas/refactor_log.schema.json`) |

## Safety Model

Transforms are classified by risk:

| Class | Examples | Applied by default |
|-------|----------|-------------------|
| `safe` | Paragraph splitting, definition previews | ✅ Always |
| `moderate` | Sentence splitting | `--moderate` flag |
| `high-risk` | Table restructuring | `--high-risk` flag |

The validator will **reject** the refactor if:
- The source file has changed since analysis (hash mismatch)
- The report is older than `max_analysis_age_hours` (default: 24h)
- The report's `analysis_mode` differs from the requested mode

## Workflow

```
/mnemosyne:analyze my_doc.md
   → output/cognition_report.json

/mnemosyne:refactor --report output/cognition_report.json
   → output/refactored/my_doc.md
   → output/refactor_plan.md
   → output/refactor_log.json
```

## Requirements

Same as `/mnemosyne:analyze`. The source document must not have changed since the report was generated.
