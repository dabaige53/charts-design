#!/usr/bin/env node
// McKinsey-Grade Executive Charts & Dashboard CLI
// Thin Node.js wrapper → auto-detects Python 3 → delegates to Python scripts

const { execFileSync, execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const SKILLS_DIR = path.resolve(__dirname, "..", "skills", "executive-charts", "scripts");
const DASHBOARD_PY = path.join(SKILLS_DIR, "generate_dashboard.py");
const CHART_PY = path.join(SKILLS_DIR, "generate_chart.py");
const WORKSPACE_PY = path.join(SKILLS_DIR, "dashboard_workspace.py");
const PACKAGE_JSON = path.resolve(__dirname, "..", "package.json");

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
    npx charts-design doctor [--json]                     Verify the local CLI runtime
    npx charts-design chart --code <code> [options]        Generate single standalone chart component
    npx charts-design batch "<codes>" [options]           Batch generate chart components for AI assembly
    npx charts-design dashboard init <dir> [options]       Start an empty composable dashboard workspace
    npx charts-design dashboard add <kind> <dir> <id> ...  Add one filter, KPI, or chart component
    npx charts-design dashboard inspect <dir> [--json]     Show a bounded workspace summary
    npx charts-design dashboard validate <dir> [--strict]  Validate components without rendering
    npx charts-design dashboard build <dir> -o <file>      Strictly compile the workspace to HTML
    npx charts-design dashboard --config <config.json>    Assemble full executive dashboard from AI config
    npx charts-design from-csv <file.csv> [options]        Legacy one-step CSV generation
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

  Composable Workspace Flow:
    dashboard init <dir> --title <title> [--org <org>]
    dashboard add filter <dir> <id> --label <label> --option value=label
    dashboard add kpi <dir> <id> --label <label> --value <value> --unit <unit>
    dashboard add chart <dir> <id> --code <code> --title <title> --data-file <data.json>
    dashboard table set <dir> --from <table.json>
    dashboard inspect|validate <dir> [--json]
    dashboard build <dir> --output <file.html> [--open] [--json]

  Examples:
    # 1. Start small and add one reviewed component at a time
    npx charts-design dashboard init ./sales-board --title "销售经营看板"
    npx charts-design dashboard add chart ./sales-board regional-sales --code c01 --title "各区域销售额" --unit "万元" --data-file ./regional-sales.json
    npx charts-design dashboard validate ./sales-board --strict --json
    npx charts-design dashboard build ./sales-board --output ./dist/sales.html

    # 2. Generate standalone chart
    npx charts-design chart --code t06 --output ./dist/chart_t06.html --open

    # 3. Batch generate atomic charts for visual selection
    npx charts-design batch "c01,t06,r01,k01" --output ./dist/charts/

    # 4. Legacy full-config build
    npx charts-design dashboard --config ./my_analysis.json --output ./dist/report.html --open

    # 5. List all 52 chart taxonomy codes
    npx charts-design list
`);
}

function printDoctor(jsonMode) {
  const python = findPython();
  const pkg = JSON.parse(fs.readFileSync(PACKAGE_JSON, "utf-8"));
  const result = {
    ok: Boolean(python) && fs.existsSync(DASHBOARD_PY) && fs.existsSync(CHART_PY) && fs.existsSync(WORKSPACE_PY),
    command: "doctor",
    version: pkg.version,
    runtime: {
      node: process.version,
      python: python || null,
      offline: true,
      authRequired: false,
    },
    paths: {
      dashboardGenerator: DASHBOARD_PY,
      chartGenerator: CHART_PY,
      workspaceTool: WORKSPACE_PY,
    },
  };
  if (jsonMode) console.log(JSON.stringify(result));
  else {
    console.log(`charts-design ${result.version}`);
    console.log(`Node: ${result.runtime.node}`);
    console.log(`Python: ${result.runtime.python || "missing"}`);
    console.log(`Workspace tool: ${fs.existsSync(WORKSPACE_PY) ? "ready" : "missing"}`);
  }
  process.exit(result.ok ? 0 : 1);
}

// ── Main ──
function main() {
  const args = process.argv.slice(2);

  if (args.length === 0 || args[0] === "--help" || args[0] === "-h") {
    printHelp();
    process.exit(0);
  }

  if (args[0] === "doctor") {
    printDoctor(args.includes("--json"));
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
      if (["init", "import-csv", "inspect", "validate", "meta", "add", "table", "build"].includes(restArgs[0])) {
        targetScript = WORKSPACE_PY;
      } else {
        targetScript = DASHBOARD_PY;
      }
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
