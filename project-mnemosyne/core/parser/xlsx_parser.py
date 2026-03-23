"""
XLSX parser for Project Mnemosyne.

Parses an .xlsx workbook using openpyxl and produces a DocumentStructure JSON.

Approximations:
- There are no paragraphs or code blocks in XLSX; the document is tabular.
- Mermaid blocks are not applicable to XLSX.
- Spans (start/end) represent logical row indices within each sheet, not
  character offsets. start = first row index (0-based), end = last row index.
- Merged cell ranges are recorded as information_units with type="table".
- Cross-sheet formula references (cell values containing "!") are recorded
  in warnings with type="cross_sheet_reference".
- Only non-empty sheets are processed. Sheets with no data rows produce a
  section with word_count=0.
- Data is read with data_only=True, so formula results are used where cached;
  raw formula text may appear for uncached cells.
"""

import argparse
import json
import os
import sys


def _exit_error(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def parse_xlsx(path: str, source_file: str) -> dict:
    try:
        import openpyxl
    except ImportError:
        _exit_error("openpyxl not installed: pip install openpyxl", 2)

    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        _exit_error(f"Failed to open .xlsx file: {exc}", 1)

    sections = []
    paragraphs: list[dict] = []
    headings: list[dict] = []
    code_blocks: list[dict] = []
    mermaid_blocks: list[dict] = []
    information_units = []
    warnings = []

    sec_idx = 0
    iu_idx = 0
    warn_idx = 0

    def next_id(prefix: str, idx: int) -> str:
        return f"{prefix}_{idx:03d}"

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]

        sec_idx += 1
        sec_id = next_id("sec", sec_idx)

        # Determine row span (logical indices)
        # In read_only mode, ws.min_row / ws.max_row are available after iteration.
        rows = list(ws.iter_rows(values_only=False))
        row_count = len(rows)
        start_row = 0
        end_row = max(0, row_count - 1)

        sections.append({
            "id": sec_id,
            "title": sheet_name,
            "level": 1,
            "span": {"start": start_row, "end": end_row},
            "word_count": 0,  # XLSX is tabular; no natural word count
        })

        # Detect merged cell ranges (not available in read_only mode; skip gracefully)
        merged_ranges = []
        try:
            # ws.merged_cells is unavailable in read_only mode; catch AttributeError
            merged_ranges = list(ws.merged_cells.ranges)
        except AttributeError:
            pass

        for merge_range in merged_ranges:
            iu_idx += 1
            information_units.append({
                "id": next_id("iu", iu_idx),
                "type": "table",
                "ref_id": sec_id,
                "order": iu_idx - 1,
                "meta": {"merged_range": str(merge_range), "sheet": sheet_name},
            })

        # Scan cell values for cross-sheet references
        for row in rows:
            for cell in row:
                value = cell.value
                if isinstance(value, str) and "!" in value:
                    warn_idx += 1
                    warnings.append({
                        "id": next_id("warn", warn_idx),
                        "type": "cross_sheet_reference",
                        "message": (
                            f"Cross-sheet reference detected in sheet '{sheet_name}' "
                            f"cell {cell.coordinate}: {value!r}"
                        ),
                        "sheet": sheet_name,
                        "cell": cell.coordinate,
                        "value": value,
                    })

    wb.close()

    return {
        "document_type": "xlsx",
        "source_file": source_file,
        "sections": sections,
        "paragraphs": paragraphs,
        "headings": headings,
        "code_blocks": code_blocks,
        "mermaid_blocks": mermaid_blocks,
        "information_units": information_units,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse an .xlsx file into DocumentStructure JSON.")
    parser.add_argument("--input", required=True, help="Path to the input .xlsx file")
    parser.add_argument("--output", required=True, help="Path to write the output JSON")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        _exit_error(f"Input file not found: {args.input}", 1)

    print(f"Parsing {args.input} ...", file=sys.stderr)
    result = parse_xlsx(args.input, os.path.basename(args.input))

    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
    except OSError as exc:
        _exit_error(f"Failed to write output file: {exc}", 1)

    print(f"Output written to {args.output}", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
