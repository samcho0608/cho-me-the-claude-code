# Project Mnemosyne — Dependencies

## Fast Mode (default)

Minimum required to run `/analyze --fast` and `/refactor`.

### Python (pip install)
```
markdown-it-py>=3.0.0    # Markdown parsing
beautifulsoup4>=4.12.0   # HTML parsing
lxml>=5.0.0              # HTML parser backend for bs4
python-docx>=1.1.0       # DOCX parsing
openpyxl>=3.1.0          # XLSX parsing
networkx>=3.2.0          # Concept dependency graph
jsonschema>=4.21.0       # JSON Schema validation
```

### TypeScript / Node.js (npm install)
```
ajv@^8.12.0              # JSON Schema validation (TypeScript side)
ajv-formats@^2.1.1       # AJV format validators
typescript@^5.3.0        # TypeScript compiler
@types/node@^20.0.0      # Node.js type definitions
```

### System
- Python 3.10+
- Node.js 18+

---

## Precise Mode (--precise flag)

Additional dependencies required for rendering-based metrics.

### System
- `@mermaid-js/mermaid-cli` — install via: `npm install -g @mermaid-js/mermaid-cli`
  Used for: L_vis precise mode (SVG rendering of Mermaid diagrams)
- `playwright` — install via: `npm install playwright && npx playwright install chromium`
  Used for: L_spa precise mode (DOM bounding boxes for HTML/Markdown)

---

## Installation

### Fast mode setup
```bash
cd project-mnemosyne
pip install markdown-it-py beautifulsoup4 lxml python-docx openpyxl networkx jsonschema
npm install
```

### Precise mode additional setup
```bash
npm install -g @mermaid-js/mermaid-cli
npm install playwright
npx playwright install chromium
```

---

## Notes
- DOCX and XLSX parsers degrade gracefully if python-docx or openpyxl are missing (exit code 2)
- Mermaid CLI absence is handled gracefully (exit code 3, metrics set to null)
- Playwright absence in fast mode: no effect (not used)
- Playwright absence in precise mode: L_spa falls back to heuristic with a warning
