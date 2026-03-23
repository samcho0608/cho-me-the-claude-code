"""
report_validator.py - Refactor guard for Project Mnemosyne.

Validates a cognition_report.json before any refactoring operation is applied.

Exit codes:
  0  Report is valid, fresh, and the source hash matches.
  1  Validation failed (hash mismatch, stale report, file not found,
     cross-mode mismatch, or schema error).

On any exit code 1, the final line of stderr is always:
  Run /analyze to generate a fresh report
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROMPT_LINE = "Run /analyze to generate a fresh report"
DEFAULT_MAX_AGE_HOURS = 24


def _fail(message: str) -> None:
    """Print failure message plus prompt line, then exit 1."""
    print(message, file=sys.stderr)
    print(PROMPT_LINE, file=sys.stderr)
    sys.exit(1)


def _sha256_file(path: str) -> str:
    """Return 'sha256:<hex>' hash of the file at path."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _load_config(project_root: str) -> dict:
    """Load config/mnemosyne.json, return dict with defaults on failure."""
    config_path = os.path.join(project_root, "config", "mnemosyne.json")
    defaults = {"max_analysis_age_hours": DEFAULT_MAX_AGE_HOURS, "analysis_mode": "fast"}
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            defaults.update(data)
        except (OSError, json.JSONDecodeError):
            pass
    return defaults


# ---------------------------------------------------------------------------
# Main validation logic
# ---------------------------------------------------------------------------

def validate(report_path: str, source_path: str, mode, project_root: str) -> None:  # mode: Optional[str]
    """
    Run all validation checks. Calls _fail() (exits 1) on any problem,
    or returns normally (exits 0) when all checks pass.
    """
    config = _load_config(project_root)
    max_age_hours = float(config.get("max_analysis_age_hours", DEFAULT_MAX_AGE_HOURS))

    # Check 1: report file exists
    if not os.path.isfile(report_path):
        _fail(f"Report file not found: {report_path}")

    # Load report
    try:
        with open(report_path, "r", encoding="utf-8") as fh:
            report = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"Failed to read report: {exc}")

    # Check 2: source hash matches
    if source_path and os.path.isfile(source_path):
        expected_hash = _sha256_file(source_path)
        report_hash = report.get("source_hash", "")
        if report_hash != expected_hash:
            _fail(
                f"Source hash mismatch: report has {report_hash!r}, "
                f"current source is {expected_hash!r}"
            )
    elif source_path:
        _fail(f"Source file not found: {source_path}")

    # Check 3: report is not stale
    analyzed_at_str = report.get("analyzed_at", "")
    if analyzed_at_str:
        try:
            analyzed_at = datetime.fromisoformat(analyzed_at_str.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - analyzed_at).total_seconds() / 3600
            if age_hours > max_age_hours:
                _fail(
                    f"Report is stale: analyzed {age_hours:.1f}h ago "
                    f"(max allowed: {max_age_hours}h)"
                )
        except ValueError:
            _fail(f"Report has invalid analyzed_at timestamp: {analyzed_at_str!r}")
    else:
        _fail("Report is missing 'analyzed_at' field")

    # Check 4: cross-mode mismatch
    if mode is not None:
        report_mode = report.get("analysis_mode", "")
        if report_mode and report_mode != mode:
            _fail(
                f"Cross-mode mismatch: report was produced in '{report_mode}' mode "
                f"but --mode '{mode}' was requested"
            )

    # All checks passed
    print(f"Report validation passed: {report_path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a Mnemosyne cognition report before refactoring."
    )
    parser.add_argument("--report", required=True, help="Path to cognition_report.json")
    parser.add_argument("--source", required=False, default=None, help="Path to original source file")
    parser.add_argument(
        "--mode",
        choices=["fast", "precise"],
        default=None,
        help="Expected analysis mode (optional cross-mode check)",
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help="Project root for loading config (default: parent of this script)",
    )
    args = parser.parse_args()

    project_root = args.project_root or os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    )

    validate(
        report_path=args.report,
        source_path=args.source,
        mode=args.mode,
        project_root=project_root,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
