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
    npx charts-design dashboard [options]     Generate executive dashboard
    npx charts-design chart [options]          Generate standalone chart component
    npx charts-design list                     List all 52 chart codes

  Dashboard Options:
    --charts, -c <codes>    Comma-separated chart codes (e.g. "c01,t06,r01,fn01")
    --preset, -p <name>     Preset: executive_report | executive_monthly |
                            financial_attribution | saas_product | strategic_matrix
    --title,  -t <title>    Custom dashboard title
    --org     <name>        Organization / department name
    --output, -o <path>     Output HTML file path
    --open                  Auto-open in default browser after generation

  Chart Options:
    --code,   -c <code>     Chart taxonomy code (e.g. c01, t06, r01, fn01)
    --output, -o <path>     Output HTML file path
    --title,  -t <title>    Custom chart title
    --snippet               Print raw JS ECharts option snippet (no file output)
    --open                  Auto-open in default browser after generation

  Examples:
    npx charts-design dashboard --preset executive_monthly --output ./dist/monthly.html --open
    npx charts-design dashboard --charts "c01,t06,r01,fn01" --title "经营研判看板" --output ./dist/report.html
    npx charts-design chart --code t06 --output ./dist/chart_t06.html --open
    npx charts-design chart --code r01 --snippet
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
    case "dashboard":
    case "dash":
      targetScript = DASHBOARD_PY;
      break;
    case "chart":
      targetScript = CHART_PY;
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
