# CC Plugin Marketplace

A curated marketplace of Claude Code plugins.

---

## Plugins

### [mnemosyne](./plugins/mnemosyne/) `v0.1.0`

**Local-first cognitive load analyzer and refactoring tool for technical documents.**

Mnemosyne measures how hard a document is to read and navigate, then safely rewrites it to reduce friction.

**Skills:**
- `/mnemosyne:analyze` — score a document's cognitive load (L_txt, L_vis, L_spa, Friction Index)
- `/mnemosyne:refactor` — apply safe structural transforms based on the analysis report

**Supports:** Markdown, HTML, DOCX, XLSX

**Modes:** `fast` (no external dependencies) · `precise` (requires `npx mmdc`)

```bash
# Quick start
cd project-mnemosyne
pip install markdown-it-py
python3 core/parser/md_parser.py --input my_doc.md --output output/struct.json
python3 core/scoring/ergonomist.py --input output/struct.json --output output/ergo.json
python3 core/metrics.py --struct output/struct.json --ergo output/ergo.json --output output/scores.json
```

---

## Repository Structure

```
cc-plugin-marketplace/
├── .claude-plugin/
│   └── marketplace.json          — marketplace registry
├── plugins/
│   └── mnemosyne/
│       ├── .claude-plugin/
│       │   └── plugin.json       — plugin manifest
│       └── skills/
│           ├── analyze/SKILL.md  — /mnemosyne:analyze slash command
│           └── refactor/SKILL.md — /mnemosyne:refactor slash command
└── project-mnemosyne/            — full implementation
    ├── commands/                 — TypeScript orchestrators
    ├── core/                     — Python analysis modules
    ├── skills/                   — Python scoring engines
    ├── fixtures/                 — test documents
    └── README.md                 — full technical documentation
```

---

## Adding a Plugin

1. Create `plugins/<name>/` with a `.claude-plugin/plugin.json`
2. Add skill directories under `plugins/<name>/skills/<skill-name>/SKILL.md`
3. Register the plugin in `.claude-plugin/marketplace.json`
