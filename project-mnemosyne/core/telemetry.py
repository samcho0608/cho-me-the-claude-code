"""
telemetry.py - Structured event logging for Project Mnemosyne.

Writes one structured line per event to output/mnemosyne.log.

Line format:
    [ISO_TIMESTAMP] [EVENT_TYPE] [MODULE] details

Supported event types:
    PARSE_SUCCESS, PARSE_FAILURE, RENDER_UNAVAILABLE, METRIC_COMPUTED,
    SUBPROCESS_TIMEOUT, VALIDATION_FAILURE, TRANSFORM_SKIPPED
"""

import json
import os
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_EVENT_TYPES = {
    "PARSE_SUCCESS",
    "PARSE_FAILURE",
    "RENDER_UNAVAILABLE",
    "METRIC_COMPUTED",
    "SUBPROCESS_TIMEOUT",
    "VALIDATION_FAILURE",
    "TRANSFORM_SKIPPED",
}

_LOG_FILE_NAME = "mnemosyne.log"


def _default_log_path() -> str:
    """Resolve output/mnemosyne.log relative to this file's project root."""
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.join(here, "..")
    return os.path.normpath(os.path.join(project_root, "output", _LOG_FILE_NAME))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_event(
    event_type: str,
    module: str,
    details,  # str or dict
    log_path=None,  # Optional[str]
) -> None:
    """
    Append a structured log line to the Mnemosyne log file.

    Args:
        event_type: One of VALID_EVENT_TYPES.
        module:     The component emitting the event (e.g. 'mermaid_engine').
        details:    A string message or a dict (serialized as compact JSON).
        log_path:   Override log file path (defaults to output/mnemosyne.log).

    Raises:
        ValueError: If event_type is not in VALID_EVENT_TYPES.
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(
            f"Unknown event type '{event_type}'. "
            f"Valid types: {sorted(VALID_EVENT_TYPES)}"
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    if isinstance(details, dict):
        detail_str = json.dumps(details, separators=(",", ":"))
    else:
        detail_str = str(details)

    line = f"[{timestamp}] [{event_type}] [{module}] {detail_str}\n"

    path = log_path or _default_log_path()

    # Create the output directory if needed
    log_dir = os.path.dirname(path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError as exc:
        # Never crash the caller due to logging failure; write to stderr instead.
        print(f"[telemetry] Failed to write log: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI (for testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    cli = argparse.ArgumentParser(description="Emit a test telemetry event.")
    cli.add_argument("--event", default="METRIC_COMPUTED")
    cli.add_argument("--module", default="cli")
    cli.add_argument("--details", default="test event")
    cli.add_argument("--log-path")
    args = cli.parse_args()

    log_event(args.event, args.module, args.details, log_path=args.log_path)
    print(f"Logged [{args.event}] from [{args.module}]")
