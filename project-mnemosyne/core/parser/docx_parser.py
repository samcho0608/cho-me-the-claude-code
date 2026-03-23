"""
DOCX parser for Project Mnemosyne.

Parses a .docx file using python-docx and produces a DocumentStructure JSON.

Approximations:
- Spans (start/end) are heuristic ordinal character offsets computed by
  summing the lengths of all preceding paragraph texts (plus one for a
  newline separator). They do not correspond to byte positions in the .docx
  archive.
- word_count is computed by splitting stripped paragraph text on whitespace.
- sentence_count is a heuristic: splits on '. ', '? ', '! ' sequences.
- Heading level is parsed from the paragraph style name (e.g. "Heading 1" -> 1).
- Mermaid blocks are not supported in DOCX and are always empty.
- Page positions are not available; ordinal index is used instead.
- Tables are recorded as information_units with type="table" but cell
  content is not extracted.
"""

import argparse
import json
import os
import re
import sys


def _exit_error(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def _word_count(text: str) -> int:
    return len(text.split())


def _sentence_count(text: str) -> int:
    sentences = re.split(r'[.?!]\s+', text.strip())
    return max(1, len([s for s in sentences if s.strip()]))


def _heading_level(style_name: str) -> int | None:
    """Return heading level 1-6 if the style is a heading, else None."""
    match = re.match(r"heading\s+(\d+)", style_name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def parse_docx(path: str, source_file: str) -> dict:
    try:
        import docx
    except ImportError:
        _exit_error("python-docx not installed: pip install python-docx", 2)

    try:
        document = docx.Document(path)
    except Exception as exc:
        _exit_error(f"Failed to open .docx file: {exc}", 1)

    sections = []
    paragraphs = []
    headings = []
    code_blocks: list[dict] = []
    mermaid_blocks: list[dict] = []
    information_units = []

    sec_idx = 0
    para_idx = 0
    h_idx = 0
    iu_idx = 0

    current_section_id = None
    char_offset = 0  # running heuristic character offset

    def next_id(prefix: str, idx: int) -> str:
        return f"{prefix}_{idx:03d}"

    # python-docx iterates body elements in order, but document.paragraphs
    # does not include table paragraphs at the top level. We iterate body
    # children directly to preserve tables in DOM order.
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    body = document.element.body

    for child in body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if tag == "p":
            para_obj = Paragraph(child, document)
            text = para_obj.text
            style_name = para_obj.style.name if para_obj.style else ""
            level = _heading_level(style_name)
            text_len = len(text)
            start = char_offset
            end = char_offset + text_len
            char_offset = end + 1  # +1 for implicit newline

            if level is not None:
                h_idx += 1
                sec_idx += 1
                h_id = next_id("h", h_idx)
                sec_id = next_id("sec", sec_idx)

                headings.append({
                    "id": h_id,
                    "level": level,
                    "text": text,
                    "span": {"start": start, "end": end},
                })
                sections.append({
                    "id": sec_id,
                    "title": text,
                    "level": level,
                    "span": {"start": start, "end": end},
                    "word_count": _word_count(text),
                })
                current_section_id = sec_id

                iu_idx += 1
                information_units.append({
                    "id": next_id("iu", iu_idx),
                    "type": "heading",
                    "ref_id": h_id,
                    "order": iu_idx - 1,
                })
            else:
                if not text.strip():
                    continue  # skip empty body paragraphs
                para_idx += 1
                para_id = next_id("para", para_idx)
                paragraphs.append({
                    "id": para_id,
                    "section_id": current_section_id,
                    "text": text,
                    "word_count": _word_count(text),
                    "sentence_count": _sentence_count(text),
                    "span": {"start": start, "end": end},
                })
                iu_idx += 1
                information_units.append({
                    "id": next_id("iu", iu_idx),
                    "type": "paragraph",
                    "ref_id": para_id,
                    "order": iu_idx - 1,
                })

        elif tag == "tbl":
            iu_idx += 1
            information_units.append({
                "id": next_id("iu", iu_idx),
                "type": "table",
                "ref_id": None,
                "order": iu_idx - 1,
            })

    return {
        "document_type": "docx",
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
    parser = argparse.ArgumentParser(description="Parse a .docx file into DocumentStructure JSON.")
    parser.add_argument("--input", required=True, help="Path to the input .docx file")
    parser.add_argument("--output", required=True, help="Path to write the output JSON")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        _exit_error(f"Input file not found: {args.input}", 1)

    print(f"Parsing {args.input} ...", file=sys.stderr)
    result = parse_docx(args.input, os.path.basename(args.input))

    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
    except OSError as exc:
        _exit_error(f"Failed to write output file: {exc}", 1)

    print(f"Output written to {args.output}", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
