# IPC Protocol: TypeScript ↔ Python Communication

## Overview

`commands/analyze.ts` and `commands/refactor.ts` orchestrate the analysis pipeline by spawning
Python modules as child processes. This document defines the protocol for that communication.

---

## Protocol Rules

### Stdout (machine-readable)
Each Python module writes exactly one JSON object to stdout on success.
No other output may appear on stdout (no print statements, no progress bars).

### Stderr (debug/trace only)
Python modules may write human-readable debug information to stderr.
The TypeScript orchestrator captures stderr and forwards it to `core/telemetry.py`.

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success — JSON output on stdout is valid |
| `1` | Analysis/processing error — module ran but encountered a problem |
| `2` | Invalid input — bad file path, unsupported file type, missing argument |
| `3` | Render unavailable — optional dependency (Mermaid CLI, Playwright) not installed |

### Timeout Behavior
- Default timeout: 60 seconds per subprocess call
- On timeout: orchestrator sends SIGTERM, waits 5s, sends SIGKILL if still running
- Affected metrics set to `null` in the report
- Warning added: `{"type": "timeout", "module": "<name>", "message": "subprocess timed out after 60s"}`

### Config Precedence
```
CLI flags > Environment variables > config/mnemosyne.json > hardcoded defaults
```

---

## Invocation Signatures

All modules accept `--input` and `--output` flags. The `--output` path is a temp file path
provided by the orchestrator. Modules write their JSON to that path.

```bash
python core/parser/md_parser.py --input <source_file> --output <temp/struct.json>
python core/scoring/concept_graph.py --input <temp/struct.json> --output <temp/cg.json>
python core/scoring/ergonomist.py --input <temp/struct.json> --output <temp/ergo.json>
python skills/mermaid_engine.py --input <temp/struct.json> --mode <fast|precise> --output <temp/vis.json>
python core/metrics.py --struct <temp/struct.json> --cg <temp/cg.json> --vis <temp/vis.json> --spa <temp/spa.json> --ergo <temp/ergo.json> --output <temp/scores.json> --mode <fast|precise>
python core/validation/report_validator.py --report <report.json> --source <source_file> --mode <fast|precise>
```

`spatial_mapper.ts` runs **in-process** (TypeScript, not a subprocess).

---

## Full Orchestration Sequence (analyze.ts, fast mode, Markdown input)

```
1. Detect file type → "markdown"

2. SPAWN: python core/parser/md_parser.py
   --input doc.md
   --output /tmp/mnemosyne-<uuid>/struct.json
   → exit 0 → read struct.json

3. SPAWN (parallel):
   a. python core/scoring/concept_graph.py
      --input /tmp/mnemosyne-<uuid>/struct.json
      --output /tmp/mnemosyne-<uuid>/cg.json

   b. python core/scoring/ergonomist.py
      --input /tmp/mnemosyne-<uuid>/struct.json
      --output /tmp/mnemosyne-<uuid>/ergo.json

   c. python skills/mermaid_engine.py
      --input /tmp/mnemosyne-<uuid>/struct.json
      --mode fast
      --output /tmp/mnemosyne-<uuid>/vis.json

   d. IN-PROCESS: spatial_mapper.ts heuristic mode
      input: struct.json
      output: /tmp/mnemosyne-<uuid>/spa.json

   → await all 4

4. SPAWN: python core/metrics.py
   --struct  /tmp/mnemosyne-<uuid>/struct.json
   --cg      /tmp/mnemosyne-<uuid>/cg.json
   --vis     /tmp/mnemosyne-<uuid>/vis.json
   --spa     /tmp/mnemosyne-<uuid>/spa.json
   --ergo    /tmp/mnemosyne-<uuid>/ergo.json
   --output  /tmp/mnemosyne-<uuid>/scores.json
   --mode    fast
   → exit 0 → read scores.json

5. MERGE: scores.json + struct.json + cg.json + ergo.json + vis.json + spa.json
   → validate against core/schemas/cognition_report.schema.json (AJV)
   → write output/cognition_report.json

6. GENERATE: cognition_summary.md from report

7. CLEANUP: rm -rf /tmp/mnemosyne-<uuid>/
```

### Subprocess Error Handling

| Exit code | Action |
|-----------|--------|
| 0 | Read output file, continue |
| 1 | Add structured warning; set affected metrics to null; continue |
| 2 | Add structured warning "unsupported"; set affected metrics to null; continue |
| 3 | Add structured warning "render_unavailable"; set affected metrics to null; continue |
| timeout | SIGTERM → 5s wait → SIGKILL; set affected metrics to null; add timeout warning |

---

## JSON Envelope Examples

### Parser output (struct.json)
```json
{
  "document_type": "markdown",
  "source_file": "doc.md",
  "sections": [...],
  "paragraphs": [...],
  "headings": [...],
  "code_blocks": [...],
  "mermaid_blocks": [...],
  "information_units": [...]
}
```

### Metrics output (scores.json)
```json
{
  "global_metrics": {
    "L_txt": 0.42,
    "L_vis": 0.18,
    "L_spa": 0.31,
    "C_load": 0.33
  },
  "raw_metrics": {
    "L_txt_raw": 2.14,
    "L_vis_raw": 0.60,
    "L_spa_raw": 1.24
  },
  "sections": [...],
  "warnings": []
}
```

### Error case (module exits 1)
```
stdout: {"error": "Could not resolve antecedent for term 'IPC'", "warnings": [...]}
```
Orchestrator reads `warnings` field and appends to report warnings; affected metrics → null.
