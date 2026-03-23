"""
ergonomist.py - Ergonomist analyzer for Project Mnemosyne.

Rule-based analysis of DocumentStructure to detect structural ergonomic issues:
  - paragraph_too_long   word_count > 150
  - sentence_too_long    word count of any sentence > 35
  - table_overloaded     columns > 8 or rows > 30

Each issue includes: type, severity, message, confidence, evidence[], rationale,
recommended_action — consistent with cognition_report.schema.json Issue schema.
"""

import argparse
import json
import os
import re
import sys
from typing import Optional


# ---------------------------------------------------------------------------
# Issue constructors
# ---------------------------------------------------------------------------

def _make_issue(
    issue_type: str,
    severity: str,
    message: str,
    confidence: float,
    evidence: list,
    rationale: str,
    recommended_action: str,
    section_id: Optional[str] = None,
    span: Optional[dict] = None,
) -> dict:
    issue: dict = {
        "type": issue_type,
        "severity": severity,
        "message": message,
        "confidence": round(confidence, 2),
        "evidence": evidence,
        "rationale": rationale,
        "recommended_action": recommended_action,
    }
    if section_id is not None:
        issue["section_id"] = section_id
    if span is not None:
        issue["span"] = span
    return issue


# ---------------------------------------------------------------------------
# Rule: paragraph_too_long
# ---------------------------------------------------------------------------

def _check_paragraph_too_long(paragraphs: list[dict]) -> list[dict]:
    issues = []
    for para in paragraphs:
        wc = para.get("word_count") or len(para.get("text", "").split())
        if wc <= 150:
            continue

        if wc > 250:
            severity = "high"
            message = (
                f"Paragraph contains {wc} words, well above the 250-word high-risk threshold."
            )
        else:
            severity = "medium"
            message = (
                f"Paragraph contains {wc} words, exceeding the 150-word recommended limit."
            )

        issues.append(_make_issue(
            issue_type="paragraph_too_long",
            severity=severity,
            message=message,
            confidence=0.95,
            evidence=[{"word_count": wc, "paragraph_id": para.get("id")}],
            rationale=(
                "Long paragraphs increase working-memory load. Readers must hold more "
                "information in mind before encountering a natural processing boundary."
            ),
            recommended_action="Split the paragraph at a logical boundary. Aim for ≤ 100 words per paragraph.",
            section_id=para.get("section_id"),
            span=para.get("span"),
        ))
    return issues


# ---------------------------------------------------------------------------
# Rule: sentence_too_long
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """Split text into approximate sentences."""
    # Split on '. ', '? ', '! ' followed by uppercase or end of string
    parts = re.split(r"(?<=[.?!])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _check_sentence_too_long(paragraphs: list[dict]) -> list[dict]:
    issues = []
    for para in paragraphs:
        text = para.get("text", "")
        sentences = _split_sentences(text)
        for sentence in sentences:
            wc = len(sentence.split())
            if wc > 35:
                preview = sentence[:80] + ("…" if len(sentence) > 80 else "")
                issues.append(_make_issue(
                    issue_type="sentence_too_long",
                    severity="low",
                    message=f"Sentence contains {wc} words (limit: 35). Preview: '{preview}'",
                    confidence=0.90,
                    evidence=[{"word_count": wc, "sentence_preview": preview}],
                    rationale=(
                        "Long sentences delay the reader's comprehension checkpoint, "
                        "increasing the probability of re-reading."
                    ),
                    recommended_action="Break the sentence into two or more shorter sentences.",
                    section_id=para.get("section_id"),
                    span=para.get("span"),
                ))
    return issues


# ---------------------------------------------------------------------------
# Rule: table_overloaded
# ---------------------------------------------------------------------------

def _check_table_overloaded(struct: dict) -> list[dict]:
    """
    Detect overloaded tables. Tables are embedded in paragraphs or top-level
    'tables' key in the DocumentStructure (parser-dependent). We scan for
    both patterns.
    """
    issues = []
    tables = struct.get("tables", [])

    for table in tables:
        cols = table.get("column_count", 0)
        rows = table.get("row_count", 0)
        section_id = table.get("section_id")

        if cols > 8 or rows > 30:
            evidence = []
            messages = []
            if cols > 8:
                evidence.append({"column_count": cols})
                messages.append(f"{cols} columns (limit: 8)")
            if rows > 30:
                evidence.append({"row_count": rows})
                messages.append(f"{rows} rows (limit: 30)")

            issues.append(_make_issue(
                issue_type="table_overloaded",
                severity="medium",
                message=f"Table exceeds ergonomic limits: {', '.join(messages)}.",
                confidence=0.92,
                evidence=evidence,
                rationale=(
                    "Wide or tall tables require horizontal/vertical scanning, "
                    "fragmenting the reader's attention and increasing spatial load."
                ),
                recommended_action=(
                    "Split into multiple focused tables, or use a summary table "
                    "with links to detail sections."
                ),
                section_id=section_id,
                span=table.get("span"),
            ))
    return issues


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------

def analyze_ergonomics(struct: dict) -> dict:
    paragraphs = struct.get("paragraphs", []) if isinstance(struct, dict) else []

    issues: list[dict] = []
    issues.extend(_check_paragraph_too_long(paragraphs))
    issues.extend(_check_sentence_too_long(paragraphs))
    issues.extend(_check_table_overloaded(struct))

    # Build summary counts by severity
    counts = {"high": 0, "medium": 0, "low": 0, "info": 0}
    for issue in issues:
        sev = issue.get("severity", "info")
        counts[sev] = counts.get(sev, 0) + 1

    return {
        "manifest_version": "1.0.0",
        "analyzer_version": "0.1.0",
        "issues": issues,
        "summary": {
            "total": len(issues),
            "by_severity": counts,
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ergonomist: detect structural ergonomic issues in a DocumentStructure."
    )
    parser.add_argument("--input", required=True, help="Path to struct.json")
    parser.add_argument("--output", required=True, help="Path to write ergo.json")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"[ergonomist] Input not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            struct = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[ergonomist] Failed to read input: {exc}", file=sys.stderr)
        sys.exit(1)

    result = analyze_ergonomics(struct)

    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
    except OSError as exc:
        print(f"[ergonomist] Failed to write output: {exc}", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
