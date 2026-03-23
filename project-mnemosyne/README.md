# Project Mnemosyne

Local-first document analysis and refactoring tool that measures and reduces cognitive load in technical documents.

---

## Overview

Mnemosyne analyzes technical documents (Markdown, HTML, DOCX, XLSX) and computes a **Friction Index** — a composite score (0–100) representing how hard a document is to read and navigate. It then applies safe, reviewer-approved transformations to reduce that score.

---

## Architecture

```
CLI (TypeScript)
├── commands/analyze.ts      — orchestrator; spawns Python subprocesses
└── commands/refactor.ts     — safe transformation applier

Python subprocesses (JSON-over-filesystem IPC)
├── core/parser/             — one parser per file type
├── core/scoring/
│   ├── concept_graph.py     — Ontologist: forward-reference detection
│   └── ergonomist.py        — Ergonomist: structural rule checks
├── skills/
│   ├── mermaid_engine.py    — visual complexity scorer
│   └── spatial_mapper.ts    — spatial load calculator (TypeScript, in-process)
├── core/metrics.py          — weighted score aggregator
└── core/validation/
    └── report_validator.py  — refactor guard (hash, staleness, mode)
```

All intermediate results are written as JSON files to the output directory. The IPC contract is documented in `docs/ipc_protocol.md`.

---

## Metrics

### L_txt — Textual Load

Measures how hard the text itself is to read.

```
L_txt_raw = Σ (penalty_per_issue × confidence)
          + Σ (cg_forward_ref_penalty)

L_txt = min(1.0, L_txt_raw / L_txt_divisor)
```

Penalties:
- Forward reference (confidence ≥ 0.90): +0.30
- Forward reference (confidence 0.70–0.89): +0.20
- Forward reference (confidence 0.40–0.69): +0.10
- Paragraph > 250 words (high): +0.25
- Paragraph 150–250 words (medium): +0.15
- Sentence > 35 words: +0.05

### L_vis — Visual Load

Measures diagram complexity.

**Fast mode** (default):
```
L_vis_raw = edge_count / max(1, node_count)   [per diagram]
L_vis = min(1.0, L_vis_raw / 4.0)
```

**Precise mode** (requires `npx mmdc`):
```
L_vis_raw = edge_intersections² / max(1, node_count + edge_count)
```

### L_spa — Spatial Load

Measures how far apart related information units are in document order.

```
L_spa = mean(|pos_a - pos_b| / total_IUs)  [over all cross-reference pairs]
```

XLSX cross-sheet references incur an additional +0.3 penalty per pair.

### C_load — Composite Cognitive Load

```
C_load = 0.45 × L_txt + 0.30 × L_vis + 0.25 × L_spa
```

Weights are configurable in `config/mnemosyne.json`.

**Friction Index** = `round(C_load × 100)` — integer in [0, 100].

---

## Commands

### `/analyze` — Run full analysis

```bash
npx ts-node commands/analyze.ts --input <file> [--output-dir <dir>] [--precise]
```

**Flags:**
- `--input <file>` — source document (`.md`, `.html`, `.docx`, `.xlsx`)
- `--output-dir <dir>` — where to write outputs (default: `./output/`)
- `--precise` — use precise scoring mode (requires `npx mmdc` for visual scoring)

**Outputs:**
- `output/cognition_report.json` — full structured report
- `output/cognition_summary.md` — human-readable summary with top issues

### `/refactor` — Apply safe transformations

```bash
npx ts-node commands/refactor.ts --report <cognition_report.json> [--moderate] [--high-risk]
```

**Flags:**
- `--report <path>` — path to a fresh `cognition_report.json`
- `--moderate` — also apply sentence-splitting transforms
- `--high-risk` — also attempt table restructuring (experimental)

**Outputs:**
- `output/refactored/<filename>` — transformed document
- `output/refactor_plan.md` — human-readable list of changes applied and skipped
- `output/refactor_log.json` — machine-readable log (schema: `refactor_log.schema.json`)

---

## Dependencies

### Fast mode (no external services required)

| Dependency | Purpose | Install |
|-----------|---------|---------|
| `markdown-it-py` | Markdown parsing | `pip install markdown-it-py` |
| `beautifulsoup4` | HTML parsing | `pip install beautifulsoup4` |
| `python-docx` | DOCX parsing | `pip install python-docx` |
| `openpyxl` | XLSX parsing | `pip install openpyxl` |
| `typescript` | TypeScript compilation | `npm install` |
| `ts-node` | TypeScript execution | `npm install` |

### Precise mode (additional)

| Dependency | Purpose | Install |
|-----------|---------|---------|
| `@mermaid-js/mermaid-cli` | Diagram layout rendering | `npm install -g @mermaid-js/mermaid-cli` |

---

## Limitations

The following are known approximations and limitations of Mnemosyne's analysis:

1. **Concept extraction is heuristic, not exact.** The Ontologist detects forward references by matching term occurrences to heading/bold definition patterns. It cannot parse natural-language semantics. Terms with ambiguous capitalization or multiple meanings may produce false positives or false negatives.

2. **L_vis fast-mode is an edge-density approximation, not a graph crossing number.** The ratio `edge_count / node_count` approximates diagram busyness but does not compute actual edge crossings, which is NP-hard. Diagrams with many edges but a clean layout may be falsely flagged as high-load.

3. **DOCX spatial placement is heuristic.** DOCX paragraph ordering is determined by document XML order, not rendered visual position. Content in text boxes, tables, or multi-column layouts may have incorrect ordinal positions in the spatial map.

4. **XLSX semantic grouping may require workbook-specific rules.** The parser treats each row as an information unit in sheet order. Merged cells, non-contiguous data ranges, and named tables are not resolved to semantic groups without workbook-specific configuration.

5. **Confidence thresholds were calibrated on technical documentation.** Scores may be less reliable for creative writing, legal documents, or highly structured reference material (e.g., API specifications with intentional forward references).

6. **Precise mode L_vis depends on `npx mmdc` availability.** If the Mermaid CLI is not installed, the scorer exits with code 3 and L_vis falls back to null (not to fast-mode). Use `--mode fast` to guarantee a complete report.
