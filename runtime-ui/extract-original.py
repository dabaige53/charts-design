"""Build-time extraction: the existing component source remains authoritative."""
from pathlib import Path
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / 'skills' / 'executive-charts'
sys.path.insert(0, str(SKILL / 'scripts'))
from core.dashboard_template import generate_dashboard_html
from core.chart_builders import CHARTS_JS_DEFINITIONS
from core.chart_catalog import ALL_CHARTS
from core.explanations import CHART_EXPLANATIONS
from core.runtime_bundle import RUNTIME_MODULES

out = ROOT / 'runtime-ui' / 'generated'
out.mkdir(exist_ok=True)
page = generate_dashboard_html('', 'Original components')
engine = re.search(r'<script id="dashboard-engine">(.*?)</script>', page, re.S).group(1)
engine = engine[engine.index("'use strict';") + len("'use strict';"):engine.rfind('})();')]
# Mounting belongs to the shared editor, not to the old full-page bootstrap.
engine = engine[:engine.index('// runtime:lifecycle')]
engine += '\n' + RUNTIME_MODULES[0][1]
# Keep real zeroes and missing data; original visual presets must not invent values.
engine = engine.replace('parseFloat(kpi.value) || 88.6', 'Number.isFinite(Number(kpi.percent)) ? Number(kpi.percent) : (Number.isFinite(parseFloat(kpi.value)) ? parseFloat(kpi.value) : 0)')
engine = engine.replace('parseFloat(kpi.value) || 92.4', 'Number.isFinite(Number(kpi.percent)) ? Number(kpi.percent) : (Number.isFinite(parseFloat(kpi.value)) ? parseFloat(kpi.value) : 0)')
engine = engine.replace("kpi.sparkData || [81.5, 82.4, 83.0, 84.5, 85.2, 85.8, 86.2, 87.8, 85.5, 86.0, 86.4, 86.8]", 'kpi.sparkData || []')
for literal in ['+4.8% YoY', '+1.2% MoM', '+12.4%', '+18.2%', '86.8%']:
    engine = engine.replace("|| '" + literal + "'", "?? '\\u2014'")
engine = engine.replace("row[col.key] || '-'", "row[col.key] ?? '-'").replace("row[col.key] || ''", "row[col.key] ?? ''")
builders = {**CHARTS_JS_DEFINITIONS, **ALL_CHARTS}
registry = ',\n'.join(json.dumps(k) + ': (' + v + ')' for k, v in builders.items())
engine += '\nconst builders = {' + registry + '};\n'
engine += '\nconst explanations = ' + json.dumps(CHART_EXPLANATIONS, ensure_ascii=True) + ';\n'
engine += '\nreturn {DashboardApp, DashboardRenderer, TOKENS, LUCIDE_ICONS, builders, explanations, ChartDataToTableConverter};\n'
(out / 'original-engine.raw.mjs').write_text('export function createOriginalComponents(echarts, setOriginalHtml) {\n' + engine + '}\n')
css = '\n'.join(re.findall(r'<style>(.*?)</style>', page, re.S))
(out / 'original-base.css').write_text(css)
catalog = json.loads((SKILL / 'references' / 'chart_catalog.json').read_text())
(out / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=True))
provenance = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [SKILL / 'scripts/core/dashboard_template.py', SKILL / 'scripts/core/chart_builders.py', SKILL / 'scripts/core/chart_catalog.py', SKILL / 'scripts/core/explanation_dialog.py']}
(out / 'provenance.json').write_text(json.dumps({'chartCodes': sorted(builders), 'kpiTypes': ['mc%02d'%i for i in range(1,10)], 'sourceHashes':provenance}, indent=2))
print('Extracted original component engine:', len(builders), 'charts, 9 KPI types')
