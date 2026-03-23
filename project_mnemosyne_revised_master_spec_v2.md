# Revised Master Specification Prompt  
## Initialize “Project Mnemosyne” — Cognitive Load Optimizer

You are initializing a Claude Code project named **Project Mnemosyne**.

Your job is to scaffold and implement a local-first analysis/refactoring tool that treats documents as **information structures whose readability can be measured and improved**.

The project must analyze documents for **cognitive load**, produce a machine-readable report, and optionally refactor documents while preserving meaning and structure.

---

## 1. Mission

Build a document analysis and refactoring system that reduces unnecessary cognitive friction in technical and structured documents.

The system should optimize for **limited human working-memory capacity** by minimizing:
- unresolved forward references
- long dependency chains
- visually dense diagrams
- excessive distance between related information units
- oversized paragraphs / tables / sections

This is a practical engineering tool, not a theoretical demo.

---

## 2. Project Goals

The system must support two primary commands:

1. **`/analyze <file>`**
   - Parse and inspect a document
   - Compute cognitive-load metrics
   - Produce a structured report
   - Produce a human-readable summary

2. **`/refactor <analysis_report>`**
   - Read a fresh analysis report
   - Apply safe transformations to reduce cognitive load
   - Preserve meaning, links, code blocks, citations, and document intent
   - Refuse to run if the analysis report is stale or mismatched

---

## 3. Supported Inputs

Initial supported file types:
- `.md`
- `.html`
- `.docx`
- `.xlsx`

The system must use file-type-specific analysis behavior where needed.

If a metric cannot be computed for a given file type, the system must:
- emit `null` for that metric
- record a warning
- continue analysis without crashing

---

## 4. Core Cognitive Load Model

Define total document load as:

\[
C_{load} = w_{txt} L_{txt} + w_{vis} L_{vis} + w_{spa} L_{spa}
\]

Default weights:
- `w_txt = 0.45`
- `w_vis = 0.30`
- `w_spa = 0.25`

Weights must be configurable.

### 4A. Textual Load (`L_txt`)

Textual load estimates how hard it is for the reader to maintain concept dependencies across the document.

#### Signals
- unresolved or delayed references
- prerequisite concept introduced after dependent concept
- oversized paragraphs
- high technical density without local grounding
- overloaded sentences containing too many concepts

#### Definitions
- **Reference Distance**: token distance between a referring expression and its resolved antecedent
- **Technical Density**:
  \[
  \text{TechnicalDensity} = \frac{\text{domain terms} + \text{acronyms} + \text{symbols}}{\max(1, \text{tokens in local window})}
  \]

Use:
\[
L_{txt,item} = \text{ReferenceDistance} \cdot \ln(1 + \text{TechnicalDensity})
\]

Then:
\[
L_{txt} = \text{normalized sum of } L_{txt,item} + \text{structural penalties}
\]

#### Structural penalties
Add penalty if:
- paragraph > 150 words
- sentence > 35 words
- concept used before any local definition and no preview definition exists
- concept dependency order appears inverted

#### Fallback rules
If antecedent resolution confidence is low:
- mark issue with confidence score
- do not fabricate certainty
- apply reduced penalty instead of full penalty

---

### 4B. Visual Load (`L_vis`)

Visual load estimates how hard diagrams are to parse.

Do **not** claim exact graph crossing number unless the implementation truly computes it.

Use rendered-layout complexity instead.

#### Signals
- edge intersection count
- node density
- edge length variance
- label overlap
- excessive visual clutter

Primary formula:
\[
L_{vis} = \frac{(\text{edgeIntersections})^2}{\max(1, \text{nodes} + \text{edges})}
\]

Optional add-on penalties:
- label overlap penalty
- edge length variance penalty
- disconnected legend penalty

#### Scope
For Mermaid and rendered diagrams:
- render first
- compute complexity from rendered coordinates or SVG layout
- record the metric as **layout-derived**, not graph-theoretic exactness unless proven

If rendering fails:
- set visual metrics to `null`
- add warning
- continue analysis

---

### 4C. Spatial Load (`L_spa`)

Spatial load estimates how far apart related information units are in rendered space.

An **Information Unit (IU)** can be:
- paragraph
- heading
- table
- diagram
- caption
- callout
- code block
- spreadsheet range

#### HTML / rendered Markdown
Use DOM bounding boxes and viewport-relative layout.

#### DOCX
Use rendered page coordinates if available; otherwise use logical block adjacency heuristics.

#### XLSX
Use:
- cell-range distance
- sheet-switch penalty
- far-apart annotation/data penalty

#### Heuristic
If related IUs are separated by large rendered distance or require scrolling/jumping/context switching, friction rises.

Example default threshold:
- HTML / Markdown: > 400 px between primary reference and target IU => penalty
- XLSX: sheet change => explicit penalty
- DOCX: cross-page dependency => penalty

#### Formula
Implementation may use a normalized Euclidean or logical adjacency score, but must be deterministic and documented.

---

## 5. Analysis Output Contract

`/analyze` must generate:

1. `cognition_report.json`
2. `cognition_summary.md`

### Required JSON schema shape

```json
{
  "manifest_version": "1.0",
  "source_file": "docs/example.md",
  "source_hash": "sha256:...",
  "document_type": "markdown",
  "analyzed_at": "2026-03-23T00:00:00Z",
  "analyzer_version": "0.1.0",
  "global_metrics": {
    "L_txt": 0.0,
    "L_vis": 0.0,
    "L_spa": 0.0,
    "C_load": 0.0
  },
  "sections": [
    {
      "id": "sec_001",
      "title": "Example Section",
      "span": {
        "start": 0,
        "end": 120
      },
      "metrics": {
        "L_txt": 0.0,
        "L_vis": 0.0,
        "L_spa": 0.0,
        "C_load": 0.0
      },
      "issues": [
        {
          "type": "forward_reference",
          "severity": "high",
          "message": "Concept used before local definition",
          "confidence": 0.84
        }
      ]
    }
  ],
  "warnings": [],
  "unsupported": [],
  "refactor_guard": {
    "requires_hash_match": true,
    "max_analysis_age_hours": 24
  }
}
```

### Requirements
- all scores normalized to a documented range
- all uncertain findings include confidence
- all unavailable metrics explicitly set to `null`
- no invented precision

---

## 6. Refactor Output Contract

`/refactor <analysis_report>` must produce:
- `refactored/<original_filename>`
- `refactor_plan.md`
- `refactor_log.json`

The refactor log must include:
- source hash used
- analysis timestamp used
- transformations applied
- sections skipped
- unresolved warnings

---

## 7. Refactoring Invariants

When executing `/refactor`, preserve these invariants in priority order:

### Priority 1 — Semantic Preservation
- do not change factual meaning
- do not alter code semantics
- do not break links, citations, anchors, or references
- do not remove required compliance / legal / technical statements

### Priority 2 — Dependency Clarity
- reduce unresolved forward references
- introduce concepts before heavy use where practical
- if reordering is not feasible, add a one-line preview definition

### Priority 3 — Local Readability
- no paragraph over 150 words unless explicitly exempted
- split overly dense sections
- convert overloaded enumerations into structured lists or tables where appropriate

### Priority 4 — Visual Anchoring
- keep diagrams near their primary textual reference
- for HTML/Markdown: target same viewport block or within ~100 px when practical
- for non-DOM formats: use nearest logical adjacency

### Priority 5 — Progressive Disclosure
- use collapsible sections only for secondary or advanced details
- do not hide core definitions required for first-pass understanding

### Priority 6 — Signal-to-Noise
- remove semantically redundant wording
- preserve tone if it materially aids comprehension
- do not aggressively strip instructional context

---

## 8. Concept Dependency Model

Do not assume all documents form a perfect DAG.

Instead, extract a **Concept Dependency Graph**:
- prerequisite edges where confidence is sufficient
- strongly connected concept clusters where cycles exist
- likely forward references
- missing local definitions
- concept introduction order

Use partial ordering where possible.

Do not fabricate dependency certainty.

---

## 9. Commands

### `/analyze <file>`
Pipeline:
1. detect file type
2. parse structure
3. build concept/reference map
4. render if needed for layout analysis
5. compute metrics
6. generate machine-readable report
7. generate human-readable summary

### `/refactor <analysis_report>`
Pipeline:
1. validate report freshness
2. validate source hash match
3. load source document
4. build transformation plan
5. apply safe transformations
6. write output + logs

If source hash does not match, refuse refactor.

If report age exceeds freshness window, refuse refactor.

---

## 10. Required Components

Scaffold the following structure:

```text
project-mnemosyne/
├─ commands/
│  ├─ analyze.ts
│  └─ refactor.ts
├─ core/
│  ├─ metrics.py
│  ├─ parser/
│  ├─ scoring/
│  ├─ validation/
│  └─ schemas/
├─ skills/
│  ├─ mermaid_engine.py
│  └─ spatial_mapper.ts
├─ subagents/
│  ├─ ontologist.md
│  └─ ergonomist.md
├─ system_prompts/
│  ├─ ontologist.system.md
│  └─ ergonomist.system.md
├─ fixtures/
│  ├─ simple_doc.md
│  ├─ spaghetti_mermaid.md
│  └─ expected_report.json
├─ output/
└─ README.md
```

---

## 11. Required Module Responsibilities

### `metrics.py`
Implement:
- textual load scoring
- visual load scoring
- spatial load scoring
- normalization helpers
- weighted total score
- confidence-aware penalty handling

### `mermaid_engine.py`
Responsibilities:
- parse Mermaid blocks
- render diagram or consume rendered output
- estimate visual complexity from rendered layout
- compute:
  - node count
  - edge count
  - edge intersection count
  - optional label overlap
  - optional density stats

Do not overclaim exact crossing-number correctness unless exactness is actually implemented.

### `spatial_mapper.ts`
Responsibilities:
- render supported documents when possible
- extract coordinates / logical positions of information units
- return spatial relationship map
- expose deterministic output format

---

## 12. Subagents

### The Ontologist
Purpose:
- extract concept inventory
- infer prerequisite relations
- detect forward references
- identify missing local definitions
- group cyclic concept clusters

Output:
- structured concept dependency graph
- confidence-scored dependency edges
- explanation of ambiguous cases

### The Ergonomist
Purpose:
- detect wall-of-text regions
- detect poor visual grouping
- detect layout jumps and broken reading flow
- detect noisy diagrams or overloaded tables

Output:
- issue list with severity
- suggested local interventions
- uncertainty notes where applicable

---

## 13. System Prompt Requirements for Subagents

Create `system_prompts/` files for each subagent.

Each prompt must specify:
- task boundaries
- allowed inferences
- required uncertainty handling
- output schema
- refusal conditions
- no fabrication rule

Subagents must prefer:
- conservative judgment
- confidence-scored findings
- explicit “unknown” over guessing

---

## 14. Verification Rules

`/refactor` must not run unless:
- the report exists
- the report hash matches the source file
- the report is fresh according to `max_analysis_age_hours`

If any guard fails:
- stop
- explain the failure
- instruct the user to rerun `/analyze`

---

## 15. Non-Functional Requirements

- local-first by default
- deterministic outputs for identical inputs and analyzer version
- no outbound network access unless explicitly enabled
- graceful degradation on unsupported features
- preserve original input before writing refactored output
- readable logs for debugging
- medium-size documents should complete within a reasonable local runtime budget

---

## 16. Initial Implementation Task

Do the following now:

1. Scaffold the directory structure.
2. Generate `metrics.py` with documented formulas and normalization helpers.
3. Create the subagent system prompts in `system_prompts/`.
4. Create minimal fixtures for testing.
5. Implement validation logic that blocks `/refactor` when the analysis report is stale or mismatched.
6. Write a concise `README.md` explaining architecture, metrics, commands, and limitations.

---

## 17. Output Style Requirements

When generating code and files:
- prefer clarity over cleverness
- include comments where assumptions matter
- document approximations honestly
- keep interfaces small and explicit
- avoid placeholder pseudoscience language in implementation comments

---

## 18. First Response Behavior

Your first response should:
1. summarize the scaffold plan
2. generate the project structure
3. create the first-pass implementation files
4. clearly label assumptions and approximations

Do not ask for permission. Begin implementation.

---

## 19. Additional Improvement Points

### A. Standardize Severity Levels
Define severity consistently across analyzers:

- **high**: comprehension is likely broken or major reader slowdown is expected
- **medium**: noticeable reading friction or dependency confusion is likely
- **low**: polish/readability issue with limited structural impact
- **info**: useful observation with no immediate readability risk

Require each issue type to map to one of these severity levels.

---

### B. Standardize Score Normalization
Document the scoring range explicitly.

Recommended default:
- each component metric (`L_txt`, `L_vis`, `L_spa`) normalized to **0.0 – 1.0**
- `C_load` normalized to **0.0 – 1.0**
- optionally expose a derived **0 – 100 readability friction index** for UI display

Avoid mixing raw and normalized values without clear labeling.

Suggested rule:
- raw metrics stored under `raw_metrics`
- normalized metrics stored under `metrics`

---

### C. Add File-Type-Specific Refactor Strategies
Refactoring should vary by document type.

#### Markdown
- reorder headings where safe
- insert preview definitions
- add summary blocks
- wrap advanced details in `<details>`
- colocate Mermaid diagrams with nearby explanation

#### HTML
- preserve IDs/anchors
- refactor DOM order conservatively
- maintain semantic tags
- avoid breaking styling hooks

#### DOCX
- preserve heading styles
- preserve numbering
- preserve tables and captions
- use logical adjacency when pixel-accurate placement is unavailable

#### XLSX
- add summary sheet when workbook is overloaded
- group related ranges/sheets
- add legends and definitions close to data
- reduce cross-sheet dependency where possible
- avoid destructive structural edits unless explicitly enabled

---

### D. Add Test Specifications
Create explicit test cases for each major issue type.

Minimum fixtures:
1. forward reference sample
2. oversized paragraph sample
3. spaghetti Mermaid sample
4. overloaded table sample
5. multi-sheet XLSX dependency sample
6. missing local definition sample
7. low-confidence concept dependency sample

For each fixture, define:
- intended issue types
- expected severity
- expected metric directionality
- known limitations

---

### E. Add Confidence Calibration Rules
Confidence scores should not be arbitrary.

Require:
- confidence based on observable signals
- documented heuristics for confidence assignment
- confidence bands such as:
  - `0.90–1.00`: strong evidence
  - `0.70–0.89`: likely
  - `0.40–0.69`: plausible but uncertain
  - `<0.40`: weak evidence, avoid strong claims

Low-confidence findings should never drive aggressive refactors by themselves.

---

### F. Add Transform Safety Classes
Not all transformations have the same risk.

Classify refactor actions as:

- **safe**: formatting-only, locality improvements, paragraph splitting without meaning change
- **moderate**: reordering subsections, inserting preview definitions, converting text to tables/lists
- **high-risk**: major structure reordering, summarization, removal of explanatory content, spreadsheet sheet restructuring

Default behavior:
- auto-apply only **safe**
- require explicit opt-in or elevated mode for **moderate**
- never auto-apply **high-risk** without explicit user approval

---

### G. Add an Explanation Layer
Each analysis result should explain **why** a score is high.

Add fields like:
- `evidence`
- `rationale`
- `recommended_action`

Example:
```json
{
  "type": "forward_reference",
  "severity": "high",
  "message": "Concept used before local definition",
  "confidence": 0.84,
  "evidence": ["term appears 3 paragraphs before first definition"],
  "rationale": "reader must retain unresolved concept across multiple paragraphs",
  "recommended_action": "add one-line preview definition or move definition earlier"
}
```

This makes the system more debuggable and more trustworthy.

---

### H. Add Versioned Schemas
Schemas should be explicit and versioned.

Recommended:
- `schemas/cognition_report.schema.json`
- `schemas/refactor_log.schema.json`
- `schemas/concept_graph.schema.json`

Each output artifact should include:
- schema version
- analyzer version
- generator identity

This improves reproducibility and upgrade safety.

---

### I. Add Observability for the Tool Itself
The analyzer/refactor tool should emit internal telemetry/logging for debugging.

Track:
- parse success/failure
- render success/failure
- metric computation time
- unsupported feature detection
- skipped transformations
- validation failures

Keep logs local and human-readable.

---

### J. Add Explicit Limitations Section
The system should state what it cannot reliably do.

Examples:
- exact semantic dependency extraction is approximate
- exact graph crossing number may not be computed
- DOCX spatial placement may be heuristic
- XLSX semantic grouping may require workbook-specific rules
- concept extraction may be domain-sensitive

This prevents overclaiming.

---

## 20. Suggested Future Extensions

Possible later additions:
- PDF support via rendered-page extraction
- diagram-type plugins beyond Mermaid
- language-aware concept extraction
- domain glossary injection
- custom refactor policy profiles such as:
  - `technical-doc`
  - `tutorial`
  - `executive-summary`
  - `spreadsheet-audit`

---

## 21. Why This Version Is Stronger

This version improves on the original by:
1. turning abstract ideas into implementation-ready rules
2. distinguishing exact metrics from approximations
3. defining a concrete JSON contract between `/analyze` and `/refactor`
4. handling file-type-specific behavior
5. defining fallback behavior and safety constraints
6. adding normalization, severity, confidence, and schema discipline
7. making the system easier to test, debug, and trust
