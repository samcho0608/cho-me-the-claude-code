"""
metrics.py - Central scoring module for Project Mnemosyne.

Reads intermediate analysis results from five JSON files (struct, cg, vis, spa,
ergo) and computes final cognitive-load metrics (L_txt, L_vis, L_spa, C_load).

Approximations and design decisions
------------------------------------
L_txt
    Penalties are summed linearly and normalized by a fixed divisor of 3.0. This
    divisor was chosen empirically so that a document with ~10 co-occurring issues
    at full severity saturates the scale. Adjust config["normalization"]["L_txt_divisor"]
    to tune.

L_vis (fast mode)
    Uses the edge/node ratio as a cheap proxy for diagram density. This does NOT
    account for edge crossings; it merely approximates how "busy" a diagram is.

L_vis (precise mode)
    Uses edge_intersections^2 / (node_count + edge_count). This is still a heuristic
    — true crossing-number computation is NP-hard. If edge_intersections is absent
    in the data, the module falls back to the fast formula and records a warning.

L_spa
    Delegated entirely to spatial_mapper; this module trusts the pre-normalized
    value it receives. If spa.json is absent or null the component is excluded from
    C_load and a warning is emitted.

Per-section scoping
    "Within section span" is tested against issue["span"]["start"] when present,
    falling back to checking ergo/cg issue lists that carry a section_id field. If
    neither key is present, the issue is attributed to no section and appears only
    in global metrics.
"""

import argparse
import json
import os
import sys


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

_DEFAULT_WEIGHTS = {
    "w_txt": 0.45,
    "w_vis": 0.30,
    "w_spa": 0.25,
}

_DEFAULT_CONFIG = {
    "weights": _DEFAULT_WEIGHTS,
    "normalization": {
        "L_txt_divisor": 3.0,
    },
}


def _load_config(config_path=None, script_dir=None):
    """Return merged config dict. Priority: --config arg > script-relative default > hardcoded."""
    candidates = []
    if config_path:
        candidates.append(config_path)
    if script_dir:
        candidates.append(os.path.join(script_dir, "..", "config", "mnemosyne.json"))

    for path in candidates:
        path = os.path.normpath(path)
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                # Merge with defaults so callers can rely on all keys existing.
                merged = json.loads(json.dumps(_DEFAULT_CONFIG))
                if "weights" in data:
                    merged["weights"].update(data["weights"])
                if "normalization" in data:
                    merged["normalization"].update(data["normalization"])
                return merged
            except (OSError, json.JSONDecodeError):
                pass  # fall through to next candidate

    return json.loads(json.dumps(_DEFAULT_CONFIG))


# ---------------------------------------------------------------------------
# JSON file loading
# ---------------------------------------------------------------------------

def _load_json(path, component_name, warnings):
    """Load JSON from path. Returns (data, ok). Appends warning if file missing."""
    if path is None or not os.path.isfile(path):
        warnings.append({
            "type": "missing_input_file",
            "module": "metrics",
            "message": f"Input file for component '{component_name}' not found"
            + (f": {path}" if path else " (no path provided)"),
        })
        return None, False
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), True
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"[metrics] JSON parse error in {path}: {exc}\n")
        sys.exit(1)
    except OSError as exc:
        sys.stderr.write(f"[metrics] Cannot read {path}: {exc}\n")
        sys.exit(1)


# ---------------------------------------------------------------------------
# L_txt
# ---------------------------------------------------------------------------

def compute_L_txt(struct, cg, ergo, config, warnings):
    """
    Compute normalised textual load score in [0, 1].

    Returns (L_txt_normalized, L_txt_raw).
    Both are None if ergo is None.
    """
    if ergo is None:
        warnings.append({
            "type": "missing_component",
            "module": "metrics",
            "message": "L_txt cannot be computed: ergo.json unavailable",
        })
        return None, None

    total_penalty = 0.0

    issues = ergo.get("issues", []) if isinstance(ergo, dict) else []

    for issue in issues:
        itype = issue.get("type", "")
        confidence = float(issue.get("confidence", 0.0))
        severity = issue.get("severity", "medium")

        if itype == "forward_reference" and confidence >= 0.40:
            ref_dist = float(issue.get("reference_distance_score", 0.5))
            total_penalty += confidence * ref_dist

        elif itype == "paragraph_too_long":
            if severity == "high":
                total_penalty += 0.25
            else:
                total_penalty += 0.15

        elif itype == "sentence_too_long":
            total_penalty += 0.05

        elif itype == "missing_local_definition" and confidence >= 0.40:
            total_penalty += 0.20

    # Penalties from concept_graph forward_references (cg.json)
    if cg is not None:
        cg_refs = []
        if isinstance(cg, dict):
            cg_refs = cg.get("forward_references", [])
        for ref in cg_refs:
            conf = float(ref.get("confidence", 0.0))
            if conf >= 0.90:
                total_penalty += 0.30
            elif conf >= 0.70:
                total_penalty += 0.20
            elif conf >= 0.40:
                total_penalty += 0.10
            else:
                warnings.append({
                    "type": "low_confidence_cg_reference",
                    "module": "metrics",
                    "message": (
                        f"concept_graph forward_reference with confidence {conf:.2f} "
                        "is below threshold (0.40); ignored in L_txt"
                    ),
                })

    divisor = float(
        config.get("normalization", {}).get("L_txt_divisor", 3.0)
    )
    L_txt_raw = total_penalty
    L_txt_normalized = min(1.0, total_penalty / divisor)
    return L_txt_normalized, L_txt_raw


# ---------------------------------------------------------------------------
# L_vis
# ---------------------------------------------------------------------------

def compute_L_vis(vis, config, mode, warnings):
    """
    Compute normalised visual load score in [0, 1].

    Returns (L_vis_normalized, L_vis_raw, mode_label).
    """
    if vis is None:
        warnings.append({
            "type": "missing_component",
            "module": "metrics",
            "message": "L_vis cannot be computed: vis.json unavailable",
        })
        return None, None, None

    diagrams = []
    if isinstance(vis, dict):
        diagrams = vis.get("diagrams", [])
    elif isinstance(vis, list):
        diagrams = vis

    # Filter to diagrams that have usable data
    valid_diagrams = [d for d in diagrams if d is not None and isinstance(d, dict)]

    if not valid_diagrams:
        return 0.0, 0.0, f"{mode}-heuristic"

    diagram_scores = []
    mode_label = f"{mode}-heuristic"
    used_fallback = False

    for diagram in valid_diagrams:
        node_count = float(diagram.get("node_count", 0))
        edge_count = float(diagram.get("edge_count", 0))

        if mode == "precise":
            if "edge_intersections" in diagram:
                intersections = float(diagram["edge_intersections"])
                score = (intersections ** 2) / max(1.0, node_count + edge_count)
            else:
                # Fall back to fast formula; record warning once
                if not used_fallback:
                    warnings.append({
                        "type": "precise_mode_fallback",
                        "module": "metrics",
                        "message": (
                            "edge_intersections missing in one or more diagrams; "
                            "falling back to fast-mode formula for those diagrams"
                        ),
                    })
                    used_fallback = True
                score = edge_count / max(1.0, node_count)
        else:
            # fast mode
            score = edge_count / max(1.0, node_count)

        diagram_scores.append(score)

    L_vis_raw = sum(diagram_scores) / len(diagram_scores)  # mean of raw per-diagram scores
    max_score = max(diagram_scores)

    if max_score == 0.0:
        L_vis_normalized = 0.0
    else:
        normalized_scores = [s / max_score for s in diagram_scores]
        L_vis_normalized = sum(normalized_scores) / len(normalized_scores)

    return L_vis_normalized, L_vis_raw, mode_label


# ---------------------------------------------------------------------------
# L_spa
# ---------------------------------------------------------------------------

def compute_L_spa(spa, config, warnings):
    """
    Read pre-normalised spatial load directly from spa.json.

    Returns (L_spa, L_spa_raw) where both values are the same pre-normalized score,
    or (None, None) if unavailable.
    """
    if spa is None:
        warnings.append({
            "type": "missing_component",
            "module": "metrics",
            "message": "L_spa cannot be computed: spa.json unavailable",
        })
        return None, None

    value = None
    if isinstance(spa, dict):
        value = spa.get("L_spa_global", spa.get("L_spa", None))
    elif isinstance(spa, (int, float)):
        value = float(spa)

    if value is None:
        warnings.append({
            "type": "missing_component",
            "module": "metrics",
            "message": "spa.json present but L_spa_global key not found; treating L_spa as null",
        })
        return None, None

    return float(value), float(value)


# ---------------------------------------------------------------------------
# C_load
# ---------------------------------------------------------------------------

def compute_C_load(L_txt, L_vis, L_spa, weights, warnings):
    """
    Compute composite cognitive load.

    None values are treated as 0.0 with a warning already added by callers.
    """
    w_txt = float(weights.get("w_txt", 0.45))
    w_vis = float(weights.get("w_vis", 0.30))
    w_spa = float(weights.get("w_spa", 0.25))

    effective_txt = L_txt if L_txt is not None else 0.0
    effective_vis = L_vis if L_vis is not None else 0.0
    effective_spa = L_spa if L_spa is not None else 0.0

    return w_txt * effective_txt + w_vis * effective_vis + w_spa * effective_spa


# ---------------------------------------------------------------------------
# Per-section helpers
# ---------------------------------------------------------------------------

def _issue_in_span(issue, span_start, span_end):
    """Return True if the issue falls within [span_start, span_end)."""
    span = issue.get("span")
    if span is not None:
        issue_start = span.get("start")
        if issue_start is not None:
            return span_start <= float(issue_start) < span_end
    return False


def _compute_section_L_txt(section, cg, ergo, config, warnings):
    """Compute L_txt scoped to a single section span."""
    span = section.get("span", {})
    span_start = float(span.get("start", 0))
    span_end = float(span.get("end", float("inf")))
    section_id = section.get("id")

    if ergo is None:
        return None, None

    total_penalty = 0.0
    issues = ergo.get("issues", []) if isinstance(ergo, dict) else []

    for issue in issues:
        # Match by span or by section_id
        in_section = False
        if "span" in issue:
            in_section = _issue_in_span(issue, span_start, span_end)
        elif section_id and issue.get("section_id") == section_id:
            in_section = True

        if not in_section:
            continue

        itype = issue.get("type", "")
        confidence = float(issue.get("confidence", 0.0))
        severity = issue.get("severity", "medium")

        if itype == "forward_reference" and confidence >= 0.40:
            ref_dist = float(issue.get("reference_distance_score", 0.5))
            total_penalty += confidence * ref_dist
        elif itype == "paragraph_too_long":
            total_penalty += 0.25 if severity == "high" else 0.15
        elif itype == "sentence_too_long":
            total_penalty += 0.05
        elif itype == "missing_local_definition" and confidence >= 0.40:
            total_penalty += 0.20

    if cg is not None:
        cg_refs = cg.get("forward_references", []) if isinstance(cg, dict) else []
        for ref in cg_refs:
            in_section = False
            if "span" in ref:
                in_section = _issue_in_span(ref, span_start, span_end)
            elif section_id and ref.get("section_id") == section_id:
                in_section = True

            if not in_section:
                continue

            conf = float(ref.get("confidence", 0.0))
            if conf >= 0.90:
                total_penalty += 0.30
            elif conf >= 0.70:
                total_penalty += 0.20
            elif conf >= 0.40:
                total_penalty += 0.10

    divisor = float(config.get("normalization", {}).get("L_txt_divisor", 3.0))
    raw = total_penalty
    normalized = min(1.0, total_penalty / divisor)
    return normalized, raw


def _compute_section_L_vis(section, vis, mode, warnings):
    """Compute L_vis scoped to a section (diagrams tagged with section_id)."""
    section_id = section.get("id")

    if vis is None:
        return None, None

    diagrams = []
    if isinstance(vis, dict):
        diagrams = vis.get("diagrams", [])
    elif isinstance(vis, list):
        diagrams = vis

    section_diagrams = [
        d for d in diagrams
        if d is not None and isinstance(d, dict)
        and d.get("section_id") == section_id
    ]

    if not section_diagrams:
        return 0.0, 0.0

    scores = []
    for diagram in section_diagrams:
        node_count = float(diagram.get("node_count", 0))
        edge_count = float(diagram.get("edge_count", 0))
        if mode == "precise" and "edge_intersections" in diagram:
            intersections = float(diagram["edge_intersections"])
            scores.append((intersections ** 2) / max(1.0, node_count + edge_count))
        else:
            scores.append(edge_count / max(1.0, node_count))

    raw = sum(scores) / len(scores)
    max_score = max(scores)
    if max_score == 0.0:
        normalized = 0.0
    else:
        normalized = sum(s / max_score for s in scores) / len(scores)
    return normalized, raw


def _compute_section_L_spa(section, spa, warnings):
    """Compute L_spa scoped to a section."""
    section_id = section.get("id")

    if spa is None:
        return None, None

    if isinstance(spa, dict):
        sections_data = spa.get("sections", [])
        for sec in sections_data:
            if isinstance(sec, dict) and sec.get("id") == section_id:
                val = sec.get("L_spa", sec.get("L_spa_global"))
                if val is not None:
                    return float(val), float(val)
        # Fall back to global value if no per-section data
        val = spa.get("L_spa_global", spa.get("L_spa"))
        if val is not None:
            return float(val), float(val)

    return None, None


def compute_per_section_metrics(struct, cg, ergo, vis, spa, config, mode, weights, warnings):
    """Return list of per-section metric dicts."""
    if struct is None:
        return []

    sections_data = []
    if isinstance(struct, dict):
        sections_data = struct.get("sections", [])
    elif isinstance(struct, list):
        sections_data = struct

    results = []
    for section in sections_data:
        if not isinstance(section, dict):
            continue

        sec_L_txt, _ = _compute_section_L_txt(section, cg, ergo, config, warnings)
        sec_L_vis, _ = _compute_section_L_vis(section, vis, mode, warnings)
        sec_L_spa, _ = _compute_section_L_spa(section, spa, warnings)
        sec_C_load = compute_C_load(sec_L_txt, sec_L_vis, sec_L_spa, weights, warnings)

        results.append({
            "id": section.get("id", ""),
            "metrics": {
                "L_txt": sec_L_txt,
                "L_vis": sec_L_vis,
                "L_spa": sec_L_spa,
                "C_load": sec_C_load,
            },
        })

    return results


# ---------------------------------------------------------------------------
# Public convenience wrapper
# ---------------------------------------------------------------------------

def compute_scores(
    struct_path=None,
    cg_path=None,
    vis_path=None,
    spa_path=None,
    ergo_path=None,
    mode="fast",
    config=None,
):
    """
    High-level wrapper callable from Python.

    Accepts file paths (or None) for each intermediate JSON, loads them,
    and returns a dict with global_metrics, raw_metrics, friction_index,
    sections, and warnings.
    """
    if config is None:
        config = _DEFAULT_CONFIG

    warnings = []
    weights = config.get("weights", _DEFAULT_WEIGHTS)

    struct, _ = _load_json(struct_path, "struct", warnings) if struct_path else (None, False)
    cg, _ = _load_json(cg_path, "cg", warnings) if cg_path else (None, False)
    vis, _ = _load_json(vis_path, "vis", warnings) if vis_path else (None, False)
    spa, _ = _load_json(spa_path, "spa", warnings) if spa_path else (None, False)
    ergo, _ = _load_json(ergo_path, "ergo", warnings) if ergo_path else (None, False)

    L_txt, L_txt_raw = compute_L_txt(struct, cg, ergo, config, warnings)
    L_vis, L_vis_raw, L_vis_mode = compute_L_vis(vis, config, mode, warnings)
    L_spa, L_spa_raw = compute_L_spa(spa, config, warnings)
    C_load = compute_C_load(L_txt, L_vis, L_spa, weights, warnings)
    friction_index = round(C_load * 100) if C_load is not None else None

    sections = compute_per_section_metrics(struct, cg, ergo, vis, spa, config, mode, weights, warnings)

    return {
        "global_metrics": {"L_txt": L_txt, "L_vis": L_vis, "L_spa": L_spa, "C_load": C_load},
        "raw_metrics": {"L_txt_raw": L_txt_raw, "L_vis_raw": L_vis_raw, "L_spa_raw": L_spa_raw, "L_vis_mode": L_vis_mode},
        "friction_index": friction_index,
        "sections": sections,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Compute cognitive-load metrics for Project Mnemosyne."
    )
    parser.add_argument("--struct", metavar="PATH", help="Path to struct.json")
    parser.add_argument("--cg", metavar="PATH", help="Path to cg.json")
    parser.add_argument("--vis", metavar="PATH", help="Path to vis.json")
    parser.add_argument("--spa", metavar="PATH", help="Path to spa.json")
    parser.add_argument("--ergo", metavar="PATH", help="Path to ergo.json")
    parser.add_argument("--output", metavar="PATH", required=True, help="Path to write scores.json")
    parser.add_argument(
        "--mode",
        choices=["fast", "precise"],
        default="fast",
        help="Analysis mode: fast (edge/node ratio) or precise (intersection-based)",
    )
    parser.add_argument("--config", metavar="PATH", help="Path to config JSON (optional)")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config = _load_config(config_path=args.config, script_dir=script_dir)
    weights = config.get("weights", _DEFAULT_WEIGHTS)

    warnings = []

    # Load all inputs; missing files become None with a warning appended.
    struct, _ = _load_json(args.struct, "struct", warnings)
    cg, _ = _load_json(args.cg, "cg", warnings)
    vis, _ = _load_json(args.vis, "vis", warnings)
    spa, _ = _load_json(args.spa, "spa", warnings)
    ergo, _ = _load_json(args.ergo, "ergo", warnings)

    # Global metrics
    L_txt, L_txt_raw = compute_L_txt(struct, cg, ergo, config, warnings)
    L_vis, L_vis_raw, L_vis_mode = compute_L_vis(vis, config, args.mode, warnings)
    L_spa, L_spa_raw = compute_L_spa(spa, config, warnings)
    C_load = compute_C_load(L_txt, L_vis, L_spa, weights, warnings)

    friction_index = round(C_load * 100) if C_load is not None else None

    # Per-section metrics
    sections = compute_per_section_metrics(
        struct, cg, ergo, vis, spa, config, args.mode, weights, warnings
    )

    output = {
        "global_metrics": {
            "L_txt": L_txt,
            "L_vis": L_vis,
            "L_spa": L_spa,
            "C_load": C_load,
        },
        "raw_metrics": {
            "L_txt_raw": L_txt_raw,
            "L_vis_raw": L_vis_raw,
            "L_spa_raw": L_spa_raw,
            "L_vis_mode": L_vis_mode,
        },
        "friction_index": friction_index,
        "sections": sections,
        "warnings": warnings,
    }

    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(output, fh, indent=2)
    except OSError as exc:
        sys.stderr.write(f"[metrics] Cannot write output file {args.output}: {exc}\n")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
