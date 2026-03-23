/**
 * spatial_mapper.ts - Spatial cognitive load calculator for Project Mnemosyne.
 *
 * Reads a DocumentStructure JSON and computes L_spa: normalized ordinal
 * distance score between information units (IUs).
 *
 * Fast mode (default, --mode fast):
 *   - Assigns each IU an ordinal position by its `order` field.
 *   - Detects cross-references in paragraph text ("see section X").
 *   - Computes distance = |pos_a - pos_b| / total_IUs for each pair.
 *   - L_spa_global = mean of all pairwise distances, clamped to [0, 1].
 *   - XLSX sheet-change penalty: +0.3 per cross-sheet reference.
 *
 * Precise mode: falls back to heuristic with a warning (browser not available).
 *
 * Output (SpatialMap JSON):
 *   { mode, iu_pairs, L_spa_global, warnings }
 */

import * as fs from "fs";
import * as path from "path";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface InformationUnit {
  id: string;
  type: string;
  ref_id?: string;
  order: number;
  section_id?: string;
  sheet?: string;
}

interface DocumentStructure {
  document_type?: string;
  information_units?: InformationUnit[];
  paragraphs?: { id: string; section_id?: string; text?: string }[];
  sections?: { id: string }[];
}

interface IUPair {
  iu_a: string;
  iu_b: string;
  ordinal_distance: number;
  normalized_distance: number;
  cross_sheet_penalty?: number;
}

interface SpatialMap {
  mode: string;
  iu_pairs: IUPair[];
  L_spa_global: number;
  warnings: { type: string; module: string; message: string }[];
}

// ---------------------------------------------------------------------------
// Cross-reference detection
// ---------------------------------------------------------------------------

function detectCrossReferences(
  struct: DocumentStructure,
  iuList: InformationUnit[]
): Array<[string, string]> {
  const pairs: Array<[string, string]> = [];
  const refById = new Map(iuList.map((iu) => [iu.ref_id ?? iu.id, iu]));
  const paragraphs = struct.paragraphs ?? [];
  const seePattern = /\bsee\s+(?:section|figure|table|step)?\s*([A-Za-z_][\w\-]*)/gi;

  for (const para of paragraphs) {
    const text = para.text ?? "";
    let match: RegExpExecArray | null;
    while ((match = seePattern.exec(text)) !== null) {
      const target = match[1].toLowerCase();
      for (const [refId, targetIU] of refById) {
        if (
          refId.toLowerCase().includes(target) ||
          target.includes(refId.toLowerCase())
        ) {
          const sourceIU = iuList.find((iu) => iu.ref_id === para.id);
          if (sourceIU && sourceIU.id !== targetIU.id) {
            pairs.push([sourceIU.id, targetIU.id]);
          }
        }
      }
    }
  }

  return pairs;
}

// ---------------------------------------------------------------------------
// Scoring
// ---------------------------------------------------------------------------

function computeSpatialLoad(
  iuList: InformationUnit[],
  crossRefs: Array<[string, string]>,
  docType: string
): { pairs: IUPair[]; L_spa_global: number } {
  if (iuList.length === 0) return { pairs: [], L_spa_global: 0.0 };

  const total = iuList.length;
  const posById = new Map(iuList.map((iu) => [iu.id, iu.order]));
  const sheetById = new Map(iuList.map((iu) => [iu.id, iu.sheet ?? ""]));
  const SHEET_PENALTY = 0.3;
  const isXlsx = docType === "xlsx";
  const pairs: IUPair[] = [];

  for (const [a, b] of crossRefs) {
    const posA = posById.get(a);
    const posB = posById.get(b);
    if (posA === undefined || posB === undefined) continue;

    const ordinalDist = Math.abs(posA - posB);
    let normalizedDist = Math.min(1.0, ordinalDist / Math.max(1, total - 1));
    let crossSheetPenalty = 0;

    if (isXlsx) {
      const sheetA = sheetById.get(a) ?? "";
      const sheetB = sheetById.get(b) ?? "";
      if (sheetA !== sheetB && (sheetA || sheetB)) {
        crossSheetPenalty = SHEET_PENALTY;
        normalizedDist = Math.min(1.0, normalizedDist + crossSheetPenalty);
      }
    }

    const pair: IUPair = {
      iu_a: a,
      iu_b: b,
      ordinal_distance: ordinalDist,
      normalized_distance: Math.round(normalizedDist * 10000) / 10000,
    };
    if (crossSheetPenalty > 0) pair.cross_sheet_penalty = crossSheetPenalty;
    pairs.push(pair);
  }

  const L_spa_global =
    pairs.length > 0
      ? Math.round(
          (pairs.reduce((s, p) => s + p.normalized_distance, 0) / pairs.length) * 10000
        ) / 10000
      : 0.0;

  return { pairs, L_spa_global };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function scoreSpatialLoad(struct: DocumentStructure, mode: string): SpatialMap {
  const warnings: SpatialMap["warnings"] = [];

  if (mode === "precise") {
    warnings.push({
      type: "precise_mode_unavailable",
      module: "spatial_mapper",
      message:
        "Precise mode requires a browser engine. Falling back to fast-heuristic.",
    });
  }

  const iuList: InformationUnit[] = (struct.information_units ?? []).map(
    (iu, idx) => ({ ...iu, order: iu.order ?? idx })
  );

  const crossRefs = detectCrossReferences(struct, iuList);
  const { pairs, L_spa_global } = computeSpatialLoad(
    iuList,
    crossRefs,
    struct.document_type ?? "markdown"
  );

  return { mode: "fast-heuristic", iu_pairs: pairs, L_spa_global, warnings };
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function main(): void {
  const args = process.argv.slice(2);
  const getArg = (flag: string): string | undefined => {
    const idx = args.indexOf(flag);
    return idx !== -1 ? args[idx + 1] : undefined;
  };

  const inputPath = getArg("--input");
  const outputPath = getArg("--output");
  const mode = getArg("--mode") ?? "fast";

  if (!inputPath || !outputPath) {
    process.stderr.write(
      "Usage: spatial_mapper.ts --input <struct.json> --output <spa.json> [--mode fast|precise]\n"
    );
    process.exit(1);
  }

  if (!fs.existsSync(inputPath)) {
    process.stderr.write(`[spatial_mapper] Input not found: ${inputPath}\n`);
    process.exit(1);
  }

  let struct: DocumentStructure;
  try {
    struct = JSON.parse(fs.readFileSync(inputPath, "utf-8"));
  } catch (err) {
    process.stderr.write(`[spatial_mapper] Failed to read input: ${err}\n`);
    process.exit(1);
  }

  const result = scoreSpatialLoad(struct, mode);

  try {
    fs.writeFileSync(outputPath, JSON.stringify(result, null, 2), "utf-8");
  } catch (err) {
    process.stderr.write(`[spatial_mapper] Failed to write output: ${err}\n`);
    process.exit(1);
  }

  process.exit(0);
}

main();
