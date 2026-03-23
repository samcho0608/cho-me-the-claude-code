---
name: analyze
description: Run Mnemosyne cognitive load analysis on a document. Detects forward references, oversized paragraphs, complex diagrams, and spatial load. Outputs cognition_report.json and a human-readable summary. Use when asked to "analyze", "score", "measure load", or "check cognitive load" of a document.
---

# Mnemosyne: Analyze

Runs the full Mnemosyne cognitive load analysis pipeline on a document and produces a structured report.

## Usage

```
/mnemosyne:analyze <file> [--output-dir <dir>] [--precise]
```

**Arguments:**
- `<file>` — path to the document to analyze (`.md`, `.html`, `.docx`, `.xlsx`)
- `--output-dir <dir>` — where to write outputs (default: `./output/`)
- `--precise` — use precise scoring mode (requires `npx mmdc` for visual diagrams)

## What It Does

Invoke the analysis pipeline from the `project-mnemosyne/` directory:

```bash
cd project-mnemosyne
npx ts-node commands/analyze.ts --input {{ARGUMENTS}}
```

If TypeScript is not compiled, run each stage directly:

```bash
# 1. Parse the document
python3 core/parser/md_parser.py --input <file> --output output/struct.json

# 2. Detect concept dependencies
python3 core/scoring/concept_graph.py --input output/struct.json --output output/cg.json

# 3. Score visual complexity (Mermaid diagrams)
python3 skills/mermaid_engine.py --input output/struct.json --mode fast --output output/vis.json

# 4. Detect structural ergonomic issues
python3 core/scoring/ergonomist.py --input output/struct.json --output output/ergo.json

# 5. Compute final metrics
python3 core/metrics.py --struct output/struct.json --cg output/cg.json \
  --vis output/vis.json --ergo output/ergo.json --output output/scores.json
```

## Output

| File | Contents |
|------|----------|
| `output/cognition_report.json` | Full structured report (schema: `core/schemas/cognition_report.schema.json`) |
| `output/cognition_summary.md` | Human-readable summary with friction index and top issues |
| `output/struct.json` | Parsed document structure |
| `output/cg.json` | Concept dependency graph |
| `output/vis.json` | Visual complexity scores |
| `output/ergo.json` | Ergonomic issue list |
| `output/scores.json` | Weighted metric scores |

## Metrics Computed

- **L_txt** — textual load: forward references, long paragraphs, long sentences
- **L_vis** — visual load: Mermaid diagram edge density
- **L_spa** — spatial load: ordinal distance between cross-referenced information units
- **C_load** — composite: `0.45×L_txt + 0.30×L_vis + 0.25×L_spa`
- **Friction Index** — `round(C_load × 100)` — integer score 0–100

## After Analysis

Run `/mnemosyne:refactor` to apply safe transformations based on this report.
Check `output/cognition_summary.md` for a human-readable overview.

## Requirements (Fast Mode)

```bash
pip install markdown-it-py beautifulsoup4 python-docx openpyxl
npm install  # from project-mnemosyne/
```
