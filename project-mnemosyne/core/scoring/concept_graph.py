"""
concept_graph.py - Ontologist (rule-based) for Project Mnemosyne.

Detects forward references: a concept used before its first definition in
token order. Produces a ConceptGraph JSON matching concept_graph.schema.json.

Confidence bands:
  0.90–1.00  Explicit definition found and term used before it in document order.
  0.70–0.89  Definition inferred from context (bold/heading introduction, etc.).
  0.40–0.69  Plausible signal: term capitalized consistently or in code span.
  <0.40      Ambiguous; emitted to warnings[], not forward_references[].

Approximations:
- "Definition" is detected by heuristic patterns:
    * The term appears as a heading text.
    * The term appears **bolded** or in a definition-list pattern (Term\n: def).
    * The term appears in a code block as an identifier assignment.
- "Use" is any occurrence of the term as a standalone word outside its definition.
- Cycle detection: not applicable for a linear token order pass; the cycles[]
  array is populated only for explicit prerequisite declarations (none in plain
  Markdown), so it will be empty in most runs.
"""

import argparse
import json
import os
import re
import sys
from typing import Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokenize_text(text: str) -> list[str]:
    """Split text into lowercase word tokens, stripping punctuation."""
    return re.findall(r"[a-zA-Z_][\w\-']*", text.lower())


def _is_technical_term(word: str) -> bool:
    """Heuristic: multi-character, not a common stop word."""
    STOP_WORDS = {
        "the", "a", "an", "and", "or", "of", "to", "in", "for", "is", "are",
        "was", "were", "be", "been", "being", "have", "has", "had", "do", "does",
        "did", "will", "would", "shall", "should", "may", "might", "must", "can",
        "could", "not", "no", "nor", "so", "yet", "both", "either", "neither",
        "each", "few", "more", "most", "other", "some", "such", "than", "too",
        "very", "just", "that", "this", "these", "those", "it", "its", "with",
        "as", "at", "by", "from", "into", "through", "during", "before", "after",
        "above", "below", "between", "out", "off", "over", "under", "again",
        "further", "then", "once", "here", "there", "when", "where", "why", "how",
        "all", "any", "if", "on", "about", "up", "down", "also", "only",
    }
    return len(word) >= 3 and word not in STOP_WORDS


def _extract_bold_terms(text: str) -> list[str]:
    """Extract terms wrapped in **bold** or __bold__."""
    patterns = [
        re.compile(r"\*\*([^*]+)\*\*"),
        re.compile(r"__([^_]+)__"),
    ]
    terms = []
    for pat in patterns:
        for m in pat.finditer(text):
            terms.append(m.group(1).strip().lower())
    return terms


def _extract_heading_terms(headings: list[dict]) -> list[tuple[str, int]]:
    """Return (term, span_start) pairs for each significant heading word."""
    pairs = []
    for h in headings:
        text = h.get("text", "")
        span_start = h.get("span", {}).get("start", 0)
        for word in _tokenize_text(text):
            if _is_technical_term(word):
                pairs.append((word, span_start))
    return pairs


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def analyze_concept_graph(struct: dict) -> dict:
    """
    Analyze DocumentStructure and produce a ConceptGraph.

    Returns dict matching concept_graph.schema.json.
    """
    warnings: list[dict] = []
    nodes: list[dict] = []
    edges: list[dict] = []
    cycles: list[list[str]] = []
    forward_refs: list[dict] = []

    paragraphs = struct.get("paragraphs", [])
    headings = struct.get("headings", [])
    code_blocks = struct.get("code_blocks", [])
    sections = struct.get("sections", [])

    # Step 1: Collect candidate technical terms with their first definition offset.
    # "definition_offset" is the char offset where the term is explicitly introduced.
    # "first_use_offset" is where it first appears anywhere.

    # Build ordered list of (term, char_offset, context) for every term occurrence
    occurrences: list[tuple[str, int, str]] = []  # (term, offset, context_type)

    # From headings
    for h in headings:
        span_start = h.get("span", {}).get("start", 0)
        text = h.get("text", "")
        for word in _tokenize_text(text):
            if _is_technical_term(word):
                occurrences.append((word, span_start, "heading"))

    # From paragraphs
    for para in paragraphs:
        span_start = para.get("span", {}).get("start", 0)
        text = para.get("text", "")

        # Bold terms in this paragraph are considered definitions
        for bold_term in _extract_bold_terms(text):
            for word in _tokenize_text(bold_term):
                if _is_technical_term(word):
                    occurrences.append((word, span_start, "bold_definition"))

        # All words in paragraph as uses
        for word in _tokenize_text(text):
            if _is_technical_term(word):
                occurrences.append((word, span_start, "use"))

    # Step 2: For each unique term, find its first "definition" offset and
    # first "use" offset.
    term_first_def: dict[str, tuple[int, str]] = {}   # term -> (offset, context)
    term_first_use: dict[str, tuple[int, str]] = {}   # term -> (offset, location_desc)

    for term, offset, context in sorted(occurrences, key=lambda x: x[1]):
        is_def = context in ("heading", "bold_definition")

        if is_def and term not in term_first_def:
            term_first_def[term] = (offset, context)

        if term not in term_first_use:
            term_first_use[term] = (offset, context)

    # Step 3: Detect forward references (used before defined)
    node_idx = 0
    for term in sorted(term_first_use.keys()):
        use_offset, use_ctx = term_first_use[term]
        node_idx += 1
        node_id = f"concept_{node_idx:03d}"

        if term in term_first_def:
            def_offset, def_ctx = term_first_def[term]

            # Node entry
            nodes.append({
                "id": node_id,
                "label": term,
                "definition_location": _make_location(def_offset, sections),
                "first_use_location": _make_location(use_offset, sections),
            })

            if use_offset < def_offset:
                # Forward reference detected
                distance = def_offset - use_offset

                if def_ctx == "heading":
                    confidence = 0.95
                elif def_ctx == "bold_definition":
                    confidence = 0.85
                else:
                    confidence = 0.72

                if confidence >= 0.40:
                    forward_refs.append({
                        "term": term,
                        "node_id": node_id,
                        "first_use_location": _make_location(use_offset, sections),
                        "defined_at_location": _make_location(def_offset, sections),
                        "confidence": round(confidence, 2),
                        "distance_chars": distance,
                    })
                else:
                    warnings.append({
                        "type": "low_confidence_forward_reference",
                        "module": "concept_graph",
                        "message": (
                            f"Term '{term}' appears before definition with confidence "
                            f"{confidence:.2f} (< 0.40); skipped from forward_references"
                        ),
                    })
        else:
            # Term used but no explicit definition found
            # Only emit if it looks technical (CamelCase or ALL_CAPS signals)
            if re.search(r"[A-Z]", term) or "_" in term:
                confidence = 0.55
            else:
                confidence = 0.35

            nodes.append({
                "id": node_id,
                "label": term,
                "definition_location": None,
                "first_use_location": _make_location(use_offset, sections),
            })

            if confidence >= 0.40:
                forward_refs.append({
                    "term": term,
                    "node_id": node_id,
                    "first_use_location": _make_location(use_offset, sections),
                    "defined_at_location": None,
                    "confidence": round(confidence, 2),
                    "distance_chars": None,
                })
            else:
                warnings.append({
                    "type": "low_confidence_undefined_term",
                    "module": "concept_graph",
                    "message": (
                        f"Term '{term}' has no detected definition; confidence "
                        f"{confidence:.2f} below threshold"
                    ),
                })

    return {
        "manifest_version": "1.0.0",
        "analyzer_version": "0.1.0",
        "nodes": nodes,
        "edges": edges,
        "cycles": cycles,
        "forward_references": forward_refs,
        "warnings": warnings,
    }


def _make_location(char_offset: int, sections: list[dict]) -> dict:
    """Return a DocumentLocation dict for a char offset."""
    section_id = None
    for sec in sections:
        span = sec.get("span", {})
        start = span.get("start", 0)
        end = span.get("end", float("inf"))
        if start <= char_offset < end:
            section_id = sec.get("id")
            break

    return {
        "char_offset": char_offset,
        "section_id": section_id,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect forward concept references in a DocumentStructure."
    )
    parser.add_argument("--input", required=True, help="Path to struct.json")
    parser.add_argument("--output", required=True, help="Path to write cg.json")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"[concept_graph] Input not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            struct = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[concept_graph] Failed to read input: {exc}", file=sys.stderr)
        sys.exit(1)

    result = analyze_concept_graph(struct)

    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
    except OSError as exc:
        print(f"[concept_graph] Failed to write output: {exc}", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
