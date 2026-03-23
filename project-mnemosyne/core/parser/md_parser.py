"""
Markdown parser for Project Mnemosyne.

Parses a Markdown file using markdown-it-py and produces a DocumentStructure JSON.

Approximations:
- Spans are approximate character offsets computed from token map (line-based).
  Character offsets are derived by summing line lengths up to the token's line number.
- word_count is computed by splitting stripped text on whitespace.
- sentence_count is a heuristic: splits on '. ', '? ', '! ' sequences.
- Section membership for paragraphs/code blocks is determined by the most recently
  seen heading at parse time (document order).
"""

import argparse
import json
import os
import sys


def _exit_error(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def _word_count(text: str) -> int:
    return len(text.split())


def _sentence_count(text: str) -> int:
    import re
    sentences = re.split(r'[.?!]\s+', text.strip())
    return max(1, len([s for s in sentences if s.strip()]))


def _char_offset(line_offsets: list[int], line: int) -> int:
    """Return character offset for a given 0-based line number."""
    if line < 0 or line >= len(line_offsets):
        return line_offsets[-1] if line_offsets else 0
    return line_offsets[line]


def _build_line_offsets(source: str) -> list[int]:
    """Return a list where index i holds the character offset of line i."""
    offsets = [0]
    for ch in source:
        if ch == '\n':
            offsets.append(offsets[-1] + 1)
        else:
            offsets[-1] += 1
    # Convert cumulative counts to start offsets
    result = [0]
    for i, length in enumerate(offsets[:-1]):
        result.append(result[-1] + length + 1)  # +1 for the newline
    return result


def parse_markdown(source: str, source_file: str) -> dict:
    try:
        from markdown_it import MarkdownIt
    except ImportError:
        _exit_error("markdown-it-py not installed: pip install markdown-it-py", 2)

    md = MarkdownIt()
    tokens = md.parse(source)

    # Build line-to-char-offset map
    lines = source.splitlines(keepends=True)
    line_start: list[int] = [0]
    for line in lines:
        line_start.append(line_start[-1] + len(line))

    def span_for(token) -> dict:
        """Compute character span from token map (line numbers)."""
        if token.map:
            start_line, end_line = token.map
            start = line_start[start_line] if start_line < len(line_start) else 0
            end = line_start[end_line] if end_line < len(line_start) else len(source)
            return {"start": start, "end": end}
        return {"start": 0, "end": len(source)}

    sections = []
    paragraphs = []
    headings = []
    code_blocks = []
    mermaid_blocks = []
    information_units = []

    sec_idx = 0
    para_idx = 0
    h_idx = 0
    cb_idx = 0
    mb_idx = 0
    iu_idx = 0

    current_section_id: str | None = None

    def next_id(prefix: str, idx: int) -> str:
        return f"{prefix}_{idx:03d}"

    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token.type == "heading_open":
            level = int(token.tag[1])  # h1 -> 1
            h_idx += 1
            sec_idx += 1
            h_id = next_id("h", h_idx)
            sec_id = next_id("sec", sec_idx)

            # Inline token is next
            inline_token = tokens[i + 1] if i + 1 < len(tokens) else None
            title_text = inline_token.content if inline_token else ""

            sp = span_for(token)
            # Heading span: just the heading line
            headings.append({
                "id": h_id,
                "level": level,
                "text": title_text,
                "span": sp,
            })

            sections.append({
                "id": sec_id,
                "title": title_text,
                "level": level,
                "span": sp,  # Will be extended below if needed
                "word_count": _word_count(title_text),
            })
            current_section_id = sec_id

            iu_idx += 1
            information_units.append({
                "id": next_id("iu", iu_idx),
                "type": "heading",
                "ref_id": h_id,
                "order": iu_idx - 1,
            })
            i += 1  # skip inline token; heading_close will be at i+2

        elif token.type == "paragraph_open":
            inline_token = tokens[i + 1] if i + 1 < len(tokens) else None
            text = inline_token.content if inline_token else ""
            sp = span_for(token)
            para_idx += 1
            para_id = next_id("para", para_idx)
            paragraphs.append({
                "id": para_id,
                "section_id": current_section_id,
                "text": text,
                "word_count": _word_count(text),
                "sentence_count": _sentence_count(text),
                "span": sp,
            })
            iu_idx += 1
            information_units.append({
                "id": next_id("iu", iu_idx),
                "type": "paragraph",
                "ref_id": para_id,
                "order": iu_idx - 1,
            })
            i += 1  # skip inline token

        elif token.type == "fence":
            lang = (token.info or "").strip().lower()
            sp = span_for(token)
            if lang == "mermaid":
                mb_idx += 1
                mb_id = next_id("mb", mb_idx)
                mermaid_blocks.append({
                    "id": mb_id,
                    "section_id": current_section_id,
                    "source": token.content,
                    "span": sp,
                })
                iu_idx += 1
                information_units.append({
                    "id": next_id("iu", iu_idx),
                    "type": "mermaid_block",
                    "ref_id": mb_id,
                    "order": iu_idx - 1,
                })
            else:
                cb_idx += 1
                cb_id = next_id("cb", cb_idx)
                code_blocks.append({
                    "id": cb_id,
                    "section_id": current_section_id,
                    "language": lang,
                    "span": sp,
                })
                iu_idx += 1
                information_units.append({
                    "id": next_id("iu", iu_idx),
                    "type": "code_block",
                    "ref_id": cb_id,
                    "order": iu_idx - 1,
                })

        i += 1

    return {
        "document_type": "markdown",
        "source_file": source_file,
        "sections": sections,
        "paragraphs": paragraphs,
        "headings": headings,
        "code_blocks": code_blocks,
        "mermaid_blocks": mermaid_blocks,
        "information_units": information_units,
        "warnings": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse a Markdown file into DocumentStructure JSON.")
    parser.add_argument("--input", required=True, help="Path to the input .md file")
    parser.add_argument("--output", required=True, help="Path to write the output JSON")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        _exit_error(f"Input file not found: {args.input}", 1)

    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            source = fh.read()
    except OSError as exc:
        _exit_error(f"Failed to read input file: {exc}", 1)

    print(f"Parsing {args.input} ...", file=sys.stderr)
    result = parse_markdown(source, os.path.basename(args.input))

    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
    except OSError as exc:
        _exit_error(f"Failed to write output file: {exc}", 1)

    print(f"Output written to {args.output}", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
