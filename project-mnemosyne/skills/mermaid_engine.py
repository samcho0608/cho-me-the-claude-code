"""
mermaid_engine.py - Visual complexity scorer for Project Mnemosyne.

Reads a DocumentStructure JSON, extracts Mermaid blocks, and computes
L_vis (visual cognitive load) scores.

Fast mode (default):
    Counts nodes and edges via regex. Computes L_vis_raw = edge_count / max(1, node_count).
    No external dependencies required.

Precise mode:
    Attempts to invoke `npx mmdc` for layout-derived metrics. Falls back with
    exit code 3 if mmdc is unavailable.

Approximations:
- Node detection: lines that match /^\s*\w[\w\s]*(\[|\(|\{|>|\|)/ or appear as
  named participants/actors in sequence diagrams.
- Edge detection: lines containing -->, ---, -., ==>, ->>, --|, etc.
- Malformed Mermaid blocks: any regex error or empty source is treated as null
  metrics with a warning appended.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile


# ---------------------------------------------------------------------------
# Regex patterns for fast-mode heuristics
# ---------------------------------------------------------------------------

_NODE_PATTERNS = [
    # Flowchart/graph node definitions: A[label], A(label), A{label}, A>label]
    re.compile(r"^\s*([A-Za-z_][\w]*)\s*[\[\(\{\|>]"),
    # Sequence/class participant/actor
    re.compile(r"^\s*(?:participant|actor|class)\s+(\w+)"),
    # State diagram state
    re.compile(r"^\s*state\s+\"[^\"]+\"\s+as\s+(\w+)"),
    re.compile(r"^\s*(\w+)\s*:\s*\w"),
]

_EDGE_PATTERNS = [
    re.compile(r"-->|---|-\.->|===>|==>|->|--\||\|--|\.\.\.|<->|<-->|\-\->>|-->>"),
]


def _count_nodes_and_edges(source: str) -> tuple[int, int]:
    """Count nodes and edges via regex heuristics."""
    lines = source.splitlines()
    seen_nodes: set[str] = set()
    edge_count = 0

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("%%"):
            continue

        # Count edges first (a line with an edge may also define nodes)
        for pat in _EDGE_PATTERNS:
            matches = pat.findall(line)
            edge_count += len(matches)
            break  # one edge per line is the norm; avoid double-counting

        # Count node declarations
        for pat in _NODE_PATTERNS:
            m = pat.match(line)
            if m:
                seen_nodes.add(m.group(1))
                break

    # Fallback: if no explicit node declarations found but edges exist,
    # count unique identifiers on edge lines as approximate nodes.
    if not seen_nodes and edge_count > 0:
        ident_pat = re.compile(r"\b([A-Za-z_][\w]*)\b")
        edge_line_pat = re.compile(r"-->|---|->|==>")
        for line in lines:
            if edge_line_pat.search(line):
                for m in ident_pat.finditer(line):
                    seen_nodes.add(m.group(1))

    return len(seen_nodes), edge_count


def _score_diagram_fast(block: dict) -> dict:
    """Compute fast-mode metrics for a single mermaid block."""
    source = block.get("source", "")
    if not source or not source.strip():
        return {
            "id": block.get("id"),
            "section_id": block.get("section_id"),
            "node_count": None,
            "edge_count": None,
            "L_vis_raw": None,
            "L_vis_normalized": None,
            "mode": "fast-heuristic",
            "warning": "Empty Mermaid block",
        }

    try:
        node_count, edge_count = _count_nodes_and_edges(source)
    except Exception as exc:
        return {
            "id": block.get("id"),
            "section_id": block.get("section_id"),
            "node_count": None,
            "edge_count": None,
            "L_vis_raw": None,
            "L_vis_normalized": None,
            "mode": "fast-heuristic",
            "warning": f"Regex error: {exc}",
        }

    L_vis_raw = edge_count / max(1, node_count)
    # Normalize: ratio > 4 is treated as saturated (1.0)
    L_vis_normalized = min(1.0, L_vis_raw / 4.0)

    return {
        "id": block.get("id"),
        "section_id": block.get("section_id"),
        "node_count": node_count,
        "edge_count": edge_count,
        "L_vis_raw": round(L_vis_raw, 4),
        "L_vis_normalized": round(L_vis_normalized, 4),
        "mode": "fast-heuristic",
    }


def _score_diagram_precise(block: dict, warnings: list) -> dict:
    """Attempt precise mode via npx mmdc. Falls back to fast on failure."""
    source = block.get("source", "")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".mmd", delete=False, encoding="utf-8"
    ) as tmp_in:
        tmp_in.write(source)
        tmp_in_path = tmp_in.name

    tmp_out_path = tmp_in_path + ".svg"

    try:
        result = subprocess.run(
            ["npx", "--yes", "mmdc", "-i", tmp_in_path, "-o", tmp_out_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"mmdc exit {result.returncode}: {result.stderr[:200]}")

        # Parse SVG to count rendered nodes (g.node) and edges (g.edgePath)
        svg_content = ""
        if os.path.isfile(tmp_out_path):
            with open(tmp_out_path, "r", encoding="utf-8") as fh:
                svg_content = fh.read()

        node_count = len(re.findall(r'class="[^"]*\bnode\b', svg_content))
        edge_count = len(re.findall(r'class="[^"]*\bedgePath\b', svg_content))
        if node_count == 0:
            raise RuntimeError("No nodes found in SVG output — mmdc may have failed silently")

        L_vis_raw = edge_count / max(1, node_count)
        L_vis_normalized = min(1.0, L_vis_raw / 4.0)

        return {
            "id": block.get("id"),
            "section_id": block.get("section_id"),
            "node_count": node_count,
            "edge_count": edge_count,
            "L_vis_raw": round(L_vis_raw, 4),
            "L_vis_normalized": round(L_vis_normalized, 4),
            "mode": "precise-layout-derived",
        }

    except FileNotFoundError:
        warnings.append({
            "type": "render_unavailable",
            "module": "mermaid_engine",
            "message": "Mermaid CLI unavailable, falling back to null",
        })
        sys.exit(3)

    except Exception as exc:
        warnings.append({
            "type": "render_failed",
            "module": "mermaid_engine",
            "message": f"mmdc rendering failed: {exc}; falling back to fast-mode",
        })
        return _score_diagram_fast(block)

    finally:
        for path in (tmp_in_path, tmp_out_path):
            try:
                os.unlink(path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def score_mermaid_blocks(struct: dict, mode: str) -> dict:
    """
    Score all Mermaid blocks in a DocumentStructure.

    Returns the vis.json output dict.
    """
    warnings: list[dict] = []
    mermaid_blocks = struct.get("mermaid_blocks", []) if isinstance(struct, dict) else []

    if not mermaid_blocks:
        return {
            "diagrams": [],
            "L_vis_global": 0.0,
            "mode": f"{mode}-heuristic",
            "warnings": warnings,
        }

    diagrams = []
    for block in mermaid_blocks:
        if mode == "precise":
            result = _score_diagram_precise(block, warnings)
        else:
            result = _score_diagram_fast(block)

        # Collect warnings from result dict
        if "warning" in result:
            warnings.append({
                "type": "diagram_warning",
                "module": "mermaid_engine",
                "diagram_id": result.get("id"),
                "message": result.pop("warning"),
            })
        diagrams.append(result)

    # Compute global L_vis as mean of valid normalized scores
    valid_scores = [
        d["L_vis_normalized"]
        for d in diagrams
        if d.get("L_vis_normalized") is not None
    ]
    L_vis_global = round(sum(valid_scores) / len(valid_scores), 4) if valid_scores else 0.0

    return {
        "diagrams": diagrams,
        "L_vis_global": L_vis_global,
        "mode": f"{mode}-heuristic" if mode == "fast" else "precise-layout-derived",
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score visual complexity of Mermaid diagrams in a DocumentStructure JSON."
    )
    parser.add_argument("--input", required=True, help="Path to struct.json (DocumentStructure)")
    parser.add_argument("--output", required=True, help="Path to write vis.json")
    parser.add_argument(
        "--mode",
        choices=["fast", "precise"],
        default="fast",
        help="fast: regex heuristic; precise: npx mmdc layout-derived",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"[mermaid_engine] Input not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            struct = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[mermaid_engine] Failed to read input: {exc}", file=sys.stderr)
        sys.exit(1)

    output = score_mermaid_blocks(struct, args.mode)

    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(output, fh, indent=2)
    except OSError as exc:
        print(f"[mermaid_engine] Failed to write output: {exc}", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
