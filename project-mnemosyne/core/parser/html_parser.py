"""
HTML parser for Project Mnemosyne.

Parses an HTML file using BeautifulSoup4 with the lxml backend and produces
a DocumentStructure JSON.

Approximations:
- Spans (start/end) are set to null because HTML rendered character offsets
  cannot be reliably determined without layout/rendering information (heuristic mode).
- word_count is computed by stripping tags and splitting on whitespace.
- sentence_count is a heuristic: splits on '. ', '? ', '! ' sequences.
- Section membership is determined by the most recently seen heading in DOM order.
- Tables are recorded as information_units with type="table" but not extracted
  as structured data.
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


def parse_html(content: str, source_file: str) -> dict:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        _exit_error("beautifulsoup4/lxml not installed", 2)

    try:
        soup = BeautifulSoup(content, "lxml")
    except Exception as exc:
        _exit_error(f"Failed to parse HTML: {exc}", 1)

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

    current_section_id = None

    NULL_SPAN = {"start": None, "end": None}

    def next_id(prefix: str, idx: int) -> str:
        return f"{prefix}_{idx:03d}"

    heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}

    # Walk all elements in document order
    body = soup.body if soup.body else soup
    for element in body.descendants:
        tag_name = getattr(element, "name", None)
        if tag_name is None:
            continue  # NavigableString

        if tag_name in heading_tags:
            level = int(tag_name[1])
            title_text = element.get_text(separator=" ", strip=True)

            h_idx += 1
            sec_idx += 1
            h_id = next_id("h", h_idx)
            sec_id = next_id("sec", sec_idx)

            headings.append({
                "id": h_id,
                "level": level,
                "text": title_text,
                "span": NULL_SPAN,
            })
            sections.append({
                "id": sec_id,
                "title": title_text,
                "level": level,
                "span": NULL_SPAN,
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

        elif tag_name == "p":
            # Skip <p> tags nested inside headings (shouldn't happen but guard)
            if element.find_parent(heading_tags):
                continue
            text = element.get_text(separator=" ", strip=True)
            if not text:
                continue

            para_idx += 1
            para_id = next_id("para", para_idx)
            paragraphs.append({
                "id": para_id,
                "section_id": current_section_id,
                "text": text,
                "word_count": _word_count(text),
                "sentence_count": _sentence_count(text),
                "span": NULL_SPAN,
            })
            iu_idx += 1
            information_units.append({
                "id": next_id("iu", iu_idx),
                "type": "paragraph",
                "ref_id": para_id,
                "order": iu_idx - 1,
            })

        elif tag_name == "pre":
            code_el = element.find("code")
            raw_text = code_el.get_text() if code_el else element.get_text()

            # Detect mermaid: class on <code> or data-lang attribute
            is_mermaid = False
            if code_el:
                classes = code_el.get("class", [])
                data_lang = code_el.get("data-lang", "")
                if "mermaid" in classes or data_lang == "mermaid":
                    is_mermaid = True
            pre_classes = element.get("class", [])
            if "mermaid" in pre_classes:
                is_mermaid = True

            if is_mermaid:
                mb_idx += 1
                mb_id = next_id("mb", mb_idx)
                mermaid_blocks.append({
                    "id": mb_id,
                    "section_id": current_section_id,
                    "source": raw_text,
                    "span": NULL_SPAN,
                })
                iu_idx += 1
                information_units.append({
                    "id": next_id("iu", iu_idx),
                    "type": "mermaid_block",
                    "ref_id": mb_id,
                    "order": iu_idx - 1,
                })
            else:
                # Detect language from class e.g. "language-python"
                lang = ""
                if code_el:
                    for cls in code_el.get("class", []):
                        if cls.startswith("language-"):
                            lang = cls[len("language-"):]
                            break
                    if not lang:
                        lang = code_el.get("data-lang", "")

                cb_idx += 1
                cb_id = next_id("cb", cb_idx)
                code_blocks.append({
                    "id": cb_id,
                    "section_id": current_section_id,
                    "language": lang,
                    "span": NULL_SPAN,
                })
                iu_idx += 1
                information_units.append({
                    "id": next_id("iu", iu_idx),
                    "type": "code_block",
                    "ref_id": cb_id,
                    "order": iu_idx - 1,
                })

        elif tag_name == "table":
            # Skip nested tables (only record outermost)
            if element.find_parent("table"):
                continue
            iu_idx += 1
            information_units.append({
                "id": next_id("iu", iu_idx),
                "type": "table",
                "ref_id": None,
                "order": iu_idx - 1,
            })

    return {
        "document_type": "html",
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
    parser = argparse.ArgumentParser(description="Parse an HTML file into DocumentStructure JSON.")
    parser.add_argument("--input", required=True, help="Path to the input HTML file")
    parser.add_argument("--output", required=True, help="Path to write the output JSON")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        _exit_error(f"Input file not found: {args.input}", 1)

    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            content = fh.read()
    except OSError as exc:
        _exit_error(f"Failed to read input file: {exc}", 1)

    print(f"Parsing {args.input} ...", file=sys.stderr)
    result = parse_html(content, os.path.basename(args.input))

    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
    except OSError as exc:
        _exit_error(f"Failed to write output file: {exc}", 1)

    print(f"Output written to {args.output}", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
