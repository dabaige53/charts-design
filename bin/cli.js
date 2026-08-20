#!/usr/bin/env node
// McKinsey-Grade Executive Charts & Dashboard CLI
// Thin Node.js wrapper → auto-detects Python 3 → delegates to Python scripts

const { execFileSync, execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const SKILLS_DIR = path.resolve(__dirname, "..", "skills", "executive-charts", "scripts");
const DASHBOARD_PY = path.join(SKILLS_DIR, "generate_dashboard.py");
const CHART_PY = path.join(SKILLS_DIR, "generate_chart.py");

// ── Detect Python 3 ──
function findPython() {
  for (const cmd of ["python3", "python"]) {
    try {
      const ver = execSync(`${cmd} --version 2>&1`, { encoding: "utf-8" }).trim();
      if (/Python 3\.\d+/.test(ver)) return cmd;
    } catch (_) {}
  }
  return null;
}

// ── Help ──
function printHelp() {
  console.log(`
  McKinsey-Grade Executive Charts & Dashboard CLI
  ================================================

  Usage:
    npx charts-design chart --code <code> [options]        Generate single standalone chart component
    npx charts-design batch "<codes>" [options]           Batch generate chart components for AI assembly
    npx charts-design dashboard --config <config.json>    Assemble full executive dashboard from AI config
    npx charts-design list                                 List all 52 chart taxonomy codes

  Chart Component Options:
    --code,   -c <code>       Chart taxonomy code (e.g. c01, t06, r01, fn01)
    --batch,  -b <codes>      Batch comma-separated codes (e.g. "c01,t06,r01,k01")
    --output, -o <path>       Output HTML file path (or output directory if --batch)
    --title,  -t <title>      Custom chart title
    --snippet                 Print raw JS ECharts option snippet (no file output)
    --open                    Auto-open in default browser after generation

  Dashboard Assembly Options:
    --config, -f <path>       Custom JSON configuration file (AI-assembled KPIs, charts, filters, table)
    --preset, -p <name>       Preset: retail_ecommerce | saas_product |
                              financial_attribution | executive_report |
                              executive_monthly | strategic_matrix | comprehensive
    --charts, -c <codes>      Comma-separated chart codes (e.g. "c01,t06,r01,fn01")
    --title,  -t <title>      Custom dashboard title
    --org     <name>          Organization / department name
    --output, -o <path>       Output HTML file path
    --open                    Auto-open in default browser after generation

  Examples:
    # 1. Generate standalone chart
    npx charts-design chart --code t06 --output ./dist/chart_t06.html --open

    # 2. Batch generate atomic charts for AI inspection and selection
    npx charts-design batch "c01,t06,r01,k01" --output ./dist/charts/

    # 3. Assemble AI-crafted full dashboard (0 Dirty Data, 100% Deterministic)
    npx charts-design dashboard --config ./my_analysis.json --output ./dist/report.html --open

    # 4. List all 52 chart taxonomy codes
    npx charts-design list
`);
}

// ── Main ──
function main() {
  const args = process.argv.slice(2);

  if (args.length === 0 || args[0] === "--help" || args[0] === "-h") {
    printHelp();
    process.exit(0);
  }

  const python = findPython();
  if (!python) {
    console.error("❌ Error: Python 3.10+ is required but not found.");
    console.error("   Install it from https://www.python.org/downloads/");
    process.exit(1);
  }

  const subcommand = args[0];
  const restArgs = args.slice(1);

  let targetScript;

  switch (subcommand) {
    case "batch":
      targetScript = CHART_PY;
      if (restArgs.length > 0 && !restArgs[0].startsWith("-")) {
        const codes = restArgs.shift();
        restArgs.unshift("--batch", codes);
      }
      break;
    case "chart":
      targetScript = CHART_PY;
      break;
    case "dashboard":
    case "dash":
      targetScript = DASHBOARD_PY;
      break;
    case "from-csv":
    case "csv":
      targetScript = DASHBOARD_PY;
      if (restArgs.length > 0 && !restArgs[0].startsWith("-")) {
        const csvPath = restArgs.shift();
        restArgs.unshift("--from-csv", csvPath);
      }
      break;
    case "list":
      targetScript = CHART_PY;
      restArgs.unshift("--list");
      break;
    default:
      console.error(`❌ Unknown subcommand: "${subcommand}"`);
      printHelp();
      process.exit(1);
  }

  if (!fs.existsSync(targetScript)) {
    console.error(`❌ Script not found: ${targetScript}`);
    console.error("   Make sure the package was installed correctly.");
    process.exit(1);
  }

  try {
    execFileSync(python, [targetScript, ...restArgs], {
      stdio: "inherit",
      cwd: process.cwd(),
    });
  } catch (err) {
    process.exit(err.status || 1);
  }
}

main();
