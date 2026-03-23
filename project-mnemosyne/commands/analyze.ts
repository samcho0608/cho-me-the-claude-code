/**
 * analyze.ts - Analysis orchestrator for Project Mnemosyne.
 *
 * Orchestrates the full cognitive load analysis pipeline:
 *   1. Parser (Python) → struct.json
 *   2. concept_graph.py (Python) → cg.json
 *   3. mermaid_engine.py (Python) → vis.json
 *   4. ergonomist.py (Python) → ergo.json
 *   5. spatial_mapper (in-process TypeScript) → spa.json
 *   6. metrics.py (Python) → scores.json
 *   7. Compose cognition_report.json
 *   8. Write cognition_summary.md
 *
 * Subprocess exit codes:
 *   0 = success
 *   1 = fatal error (pipeline aborts)
 *   2 = unsupported / unavailable → records null metric, continues
 *   3 = render unavailable → records null with warning, continues
 */

import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";
import { execFileSync, spawnSync } from "child_process";
import { scoreSpatialLoad } from "../skills/spatial_mapper";

const ANALYZER_VERSION = "0.1.0";
const MANIFEST_VERSION = "1.0.0";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseArgs(): { input: string; outputDir: string; mode: "fast" | "precise" } {
  const args = process.argv.slice(2);
  const getArg = (flag: string): string | undefined => {
    const idx = args.indexOf(flag);
    return idx !== -1 ? args[idx + 1] : undefined;
  };

  const input = getArg("--input");
  if (!input) {
    console.error("Usage: analyze.ts --input <file> [--output-dir <dir>] [--precise]");
    process.exit(1);
  }

  const outputDir = getArg("--output-dir") ?? "./output";
  const mode: "fast" | "precise" = args.includes("--precise") ? "precise" : "fast";

  return { input, outputDir, mode };
}

function sha256File(filePath: string): string {
  const content = fs.readFileSync(filePath);
  return "sha256:" + crypto.createHash("sha256").update(content).digest("hex");
}

interface SubprocessResult {
  ok: boolean;
  exitCode: number;
  stderr: string;
}

function runPython(scriptPath: string, scriptArgs: string[]): SubprocessResult {
  const result = spawnSync("python3", [scriptPath, ...scriptArgs], {
    encoding: "utf-8",
    timeout: 60000,
  });

  const exitCode = result.status ?? 1;
  const stderr = result.stderr ?? "";

  if (result.error) {
    return { ok: false, exitCode: 1, stderr: String(result.error) };
  }

  return { ok: exitCode === 0, exitCode, stderr };
}

function resolveScript(relative: string): string {
  return path.resolve(__dirname, "..", relative);
}

function loadJson(filePath: string): unknown {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf-8"));
  } catch {
    return null;
  }
}

function detectDocumentType(filePath: string): string {
  const ext = path.extname(filePath).toLowerCase();
  const map: Record<string, string> = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".htm": "html",
    ".docx": "docx",
    ".xlsx": "xlsx",
  };
  return map[ext] ?? "markdown";
}

function selectParser(docType: string): string {
  const parsers: Record<string, string> = {
    markdown: "core/parser/md_parser.py",
    html: "core/parser/html_parser.py",
    docx: "core/parser/docx_parser.py",
    xlsx: "core/parser/xlsx_parser.py",
  };
  return parsers[docType] ?? "core/parser/md_parser.py";
}

// ---------------------------------------------------------------------------
// Report composition
// ---------------------------------------------------------------------------

function buildReport(params: {
  sourceFile: string;
  sourceHash: string;
  docType: string;
  mode: "fast" | "precise";
  analyzedAt: string;
  struct: any;
  scores: any;
  warnings: any[];
  unsupported: any[];
}): object {
  const { sourceFile, sourceHash, docType, mode, analyzedAt, struct, scores, warnings, unsupported } = params;

  const globalMetrics = scores?.global_metrics ?? { L_txt: null, L_vis: null, L_spa: null, C_load: null };
  const rawMetrics = scores?.raw_metrics ?? {};
  const frictionIndex = scores?.friction_index ?? null;
  const sections = scores?.sections ?? [];
  const scoreWarnings = scores?.warnings ?? [];

  return {
    manifest_version: MANIFEST_VERSION,
    analyzer_version: ANALYZER_VERSION,
    analysis_mode: mode,
    source_file: sourceFile,
    source_hash: sourceHash,
    document_type: docType,
    analyzed_at: analyzedAt,
    global_metrics: globalMetrics,
    raw_metrics: rawMetrics,
    friction_index: frictionIndex,
    sections,
    warnings: [...warnings, ...scoreWarnings],
    unsupported,
    refactor_guard: {
      source_hash: sourceHash,
      report_generated_at: analyzedAt,
    },
  };
}

function buildSummary(report: any): string {
  const fi = report.friction_index ?? "N/A";
  const gm = report.global_metrics ?? {};
  const warnings = report.warnings ?? [];
  const unsupported = report.unsupported ?? [];

  // Collect top issues by severity
  const allWarnings = warnings.filter((w: any) => w.severity === "high" || w.type?.includes("failure"));
  const topIssues = allWarnings.slice(0, 5);

  const lines: string[] = [
    `# Mnemosyne Cognition Report Summary`,
    ``,
    `**Source:** ${report.source_file}`,
    `**Analyzed at:** ${report.analyzed_at}`,
    `**Mode:** ${report.analysis_mode}`,
    `**Friction Index:** ${fi} / 100`,
    ``,
    `## Global Metrics`,
    ``,
    `| Metric | Score |`,
    `|--------|-------|`,
    `| L_txt (textual load) | ${gm.L_txt?.toFixed(3) ?? "N/A"} |`,
    `| L_vis (visual load) | ${gm.L_vis?.toFixed(3) ?? "N/A"} |`,
    `| L_spa (spatial load) | ${gm.L_spa?.toFixed(3) ?? "N/A"} |`,
    `| C_load (composite) | ${gm.C_load?.toFixed(3) ?? "N/A"} |`,
    ``,
  ];

  if (topIssues.length > 0) {
    lines.push(`## Top Issues`);
    lines.push(``);
    for (const issue of topIssues) {
      lines.push(`- **[${issue.severity ?? issue.type ?? "warning"}]** ${issue.message ?? JSON.stringify(issue)}`);
    }
    lines.push(``);
  }

  if (unsupported.length > 0) {
    lines.push(`## Unsupported Metrics`);
    lines.push(``);
    for (const u of unsupported) {
      lines.push(`- ${u.metric ?? u}: ${u.reason ?? "unavailable"}`);
    }
    lines.push(``);
  }

  if (warnings.length > 0) {
    lines.push(`## All Warnings (${warnings.length})`);
    lines.push(``);
    for (const w of warnings.slice(0, 20)) {
      lines.push(`- [${w.type ?? "warning"}] ${w.message ?? JSON.stringify(w)}`);
    }
    if (warnings.length > 20) {
      lines.push(`- … and ${warnings.length - 20} more`);
    }
    lines.push(``);
  }

  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  const { input, outputDir, mode } = parseArgs();

  if (!fs.existsSync(input)) {
    console.error(`[analyze] Input file not found: ${input}`);
    process.exit(1);
  }

  fs.mkdirSync(outputDir, { recursive: true });

  const analyzedAt = new Date().toISOString();
  const sourceHash = sha256File(input);
  const docType = detectDocumentType(input);

  const tmp = (name: string) => path.join(outputDir, name);
  const warnings: any[] = [];
  const unsupported: any[] = [];

  console.error(`[analyze] Source: ${input} (${docType}, mode=${mode})`);

  // Step 1: Parse
  console.error("[analyze] Step 1: Parsing document...");
  const parserScript = resolveScript(selectParser(docType));
  const parseResult = runPython(parserScript, ["--input", input, "--output", tmp("struct.json")]);

  if (!parseResult.ok) {
    if (parseResult.exitCode === 2) {
      console.error(`[analyze] Parser: unsupported file type, recording null struct`);
      unsupported.push({ metric: "struct", reason: "Unsupported file type" });
    } else {
      console.error(`[analyze] Parser fatal error (exit ${parseResult.exitCode}): ${parseResult.stderr}`);
      process.exit(1);
    }
  }

  const struct = loadJson(tmp("struct.json")) as any;

  // Step 2: Concept graph
  console.error("[analyze] Step 2: Building concept graph...");
  const cgResult = runPython(resolveScript("core/scoring/concept_graph.py"), [
    "--input", tmp("struct.json"),
    "--output", tmp("cg.json"),
  ]);
  if (!cgResult.ok) {
    unsupported.push({ metric: "concept_graph", reason: cgResult.stderr.slice(0, 200) });
    warnings.push({ type: "subprocess_failure", module: "concept_graph", message: cgResult.stderr.slice(0, 200) });
  }

  // Step 3: Mermaid visual scoring
  console.error("[analyze] Step 3: Scoring visual complexity...");
  const visResult = runPython(resolveScript("skills/mermaid_engine.py"), [
    "--input", tmp("struct.json"),
    "--output", tmp("vis.json"),
    "--mode", mode,
  ]);
  if (!visResult.ok) {
    if (visResult.exitCode === 3) {
      warnings.push({ type: "render_unavailable", module: "mermaid_engine", message: "Mermaid CLI unavailable" });
    } else if (visResult.exitCode === 2) {
      unsupported.push({ metric: "L_vis", reason: "Mermaid rendering unsupported" });
    }
  }

  // Step 4: Ergonomist
  console.error("[analyze] Step 4: Running ergonomist...");
  const ergoResult = runPython(resolveScript("core/scoring/ergonomist.py"), [
    "--input", tmp("struct.json"),
    "--output", tmp("ergo.json"),
  ]);
  if (!ergoResult.ok) {
    unsupported.push({ metric: "ergo", reason: ergoResult.stderr.slice(0, 200) });
  }

  // Step 5: Spatial mapper (in-process TypeScript)
  console.error("[analyze] Step 5: Computing spatial load...");
  if (struct) {
    try {
      const spaResult = scoreSpatialLoad(struct, mode);
      fs.writeFileSync(tmp("spa.json"), JSON.stringify(spaResult, null, 2), "utf-8");
    } catch (err) {
      warnings.push({ type: "spatial_mapper_error", module: "spatial_mapper", message: String(err) });
    }
  }

  // Step 6: Metrics
  console.error("[analyze] Step 6: Computing cognitive load metrics...");
  const metricsArgs = [
    "--output", tmp("scores.json"),
    "--mode", mode,
  ];
  if (fs.existsSync(tmp("struct.json"))) metricsArgs.push("--struct", tmp("struct.json"));
  if (fs.existsSync(tmp("cg.json"))) metricsArgs.push("--cg", tmp("cg.json"));
  if (fs.existsSync(tmp("vis.json"))) metricsArgs.push("--vis", tmp("vis.json"));
  if (fs.existsSync(tmp("spa.json"))) metricsArgs.push("--spa", tmp("spa.json"));
  if (fs.existsSync(tmp("ergo.json"))) metricsArgs.push("--ergo", tmp("ergo.json"));

  const metricsResult = runPython(resolveScript("core/metrics.py"), metricsArgs);
  if (!metricsResult.ok) {
    warnings.push({ type: "metrics_error", module: "metrics", message: metricsResult.stderr.slice(0, 200) });
  }

  const scores = loadJson(tmp("scores.json"));

  // Step 7: Compose report
  console.error("[analyze] Step 7: Writing cognition report...");
  const report = buildReport({
    sourceFile: input,
    sourceHash,
    docType,
    mode,
    analyzedAt,
    struct,
    scores,
    warnings,
    unsupported,
  });

  const reportPath = path.join(outputDir, "cognition_report.json");
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf-8");
  console.error(`[analyze] Report written: ${reportPath}`);

  // Step 8: Write summary
  const summaryPath = path.join(outputDir, "cognition_summary.md");
  fs.writeFileSync(summaryPath, buildSummary(report), "utf-8");
  console.error(`[analyze] Summary written: ${summaryPath}`);

  console.log(reportPath);
  process.exit(0);
}

main().catch((err) => {
  console.error(`[analyze] Unexpected error: ${err}`);
  process.exit(1);
});
