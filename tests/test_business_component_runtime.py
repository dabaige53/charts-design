"""Exercise the generated runtime without starting a browser."""
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).parents[1] / "skills" / "executive-charts" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core.dashboard_template import generate_dashboard_html
from dashboard_workspace import validate_resolved
from generate_dashboard import CHARTS_MAP


def run_runtime(scenario):
    html = generate_dashboard_html("", "Business components")
    source = next(script for script in re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S)
                  if "class DashboardApp" in script)
    source = source.rsplit("})();", 1)[0] + "window.testAPI = {DashboardApp, DashboardRenderer, StateStore, ChartDataToTableConverter};})();"
    program = "\n".join([
        "const window = {}; const document = {readyState: 'complete'};",
        "const widgetOptions = []; const echarts = {init: () => ({setOption: option => widgetOptions.push(option), dispose() {}}), graphic: {LinearGradient: function() {}}};",
        source,
        "const {DashboardApp, DashboardRenderer, StateStore, ChartDataToTableConverter} = window.testAPI;",
        f"const columnChart = ({CHARTS_MAP['c01']});",
        scenario,
    ])
    result = subprocess.run(["node", "-e", program], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_kpi_zero_and_missing_values_never_use_business_samples():
    result = run_runtime("""
const container = {innerHTML: '', children: []};
const root = {getElementById: () => container};
const results = {};
for (const type of ['mc02', 'mc04', 'mc06', 'mc07', 'mc09']) {
  new DashboardRenderer({config: {kpis: [{id: 'metric', type, label: '指标', value: '0%', unit: '%'}]}}, root).renderKPIs();
  results[type] = container.innerHTML;
}
const app = Object.create(DashboardApp.prototype);
app.config = {kpis: [{id: 'zero', type: 'mc05', value: '0%'}]};
app.state = {chartInstances: {}}; app.getById = () => ({});
app.initKPIWidgets();
console.log(JSON.stringify({cards: results, gauge: widgetOptions[0].series[0].data[0].value}));
""")
    assert 'width: 0%;' in result['cards']['mc04']
    assert result['gauge'] == 0
    for source in result['cards'].values():
        for sample in ('+4.8%', '+12.4%', '32.8%', '72%', '28%', 'S 级标杆', 'undefined'):
            assert sample not in source


def bound_config():
    return {
        'meta': {'title': 'Sales'},
        'filters': [{'id': 'region', 'key': 'region', 'label': '区域', 'type': 'multi-select',
                     'options': [{'value': 'east'}, {'value': 'south'}], 'fields': ['region'],
                     'componentIds': ['revenue', 'sales']}],
        'kpis': [{'id': 'revenue', 'type': 'mc01', 'label': '收入', 'value': '224 万元', 'unit': '万元',
                  'binding': {'field': 'sales', 'aggregate': 'sum', 'precision': 0}}],
        'charts': [{'id': 'sales', 'code': 'c01', 'title': '区域收入', 'unit': '万元',
                    'data': {'categories': ['east', 'south'], 'values': [128, 96]},
                    'presentation': {'axisLabels': {'x': '区域', 'y': '收入'}, 'seriesLabels': ['收入'],
                                     'tooltipValueLabels': ['收入'], 'units': ['万元'],
                                     'tableHeaders': ['区域', '收入']},
                    'binding': {'groupBy': 'region', 'category': 'categories',
                                'series': {'values': {'field': 'sales', 'aggregate': 'sum'}}}}],
        'table': {'columns': [{'key': 'region', 'title': '区域'},
                              {'key': 'sales', 'title': '收入', 'unit': '万元', 'align': 'right'}],
                  'rows': [{'region': 'east', 'sales': 128}, {'region': 'south', 'sales': 96}]},
    }


def test_filter_recomputes_scoped_kpi_chart_and_export_data_then_restores():
    config = bound_config()
    result = run_runtime(f"const config = {json.dumps(config)};" + """
config.charts = config.charts.map(chart => ({...columnChart, ...chart}));
config.kpis.push({id: 'unscoped', type: 'mc01', label: 'Fixed', value: '999'});
const app = Object.create(DashboardApp.prototype);
app.state = new StateStore(config); app.config = app.state.config;
let option;
app.state.chartInstances.sales = {setOption: value => option = value};
const elements = {globalKeywordSearch: {value: ''}, chipsContainer: {innerHTML: ''},
  activeFilterBadgeCount: {}, activeChipsTray: {classList: {add() {}, remove() {}}}};
app.getById = id => elements[id] || null;
app.renderer = {renderKPIs() {}};
app.initKPIWidgets = () => {};
app.renderTableEngine = () => {};
app.query = () => null;
const result = [];
for (const selected of [['east'], [], ['east', 'south']]) {
  app.state.filterValues.region = new Set(selected);
  app.onGlobalFilterChange();
  const chart = app.config.charts[0];
  result.push({rows: app.getFilteredTableRows().length, kpi: app.config.kpis[0].value,
    fixed: app.config.kpis[1].value, values: option.series[0].data,
    table: chart.tableDataExtractor(chart.data, 'month', chart)});
}
console.log(JSON.stringify(result));
""")
    assert [(r['rows'], r['kpi'], r['values']) for r in result] == [
        (1, '128 万元', [128]), (0, '0 万元', []), (2, '224 万元', [128, 96]),
    ]
    assert all(r['fixed'] == '999' for r in result)
    assert result[0]['table']['rows'] == [['east', '128 万元']]
    assert result[1]['table']['rows'] == []


@pytest.mark.parametrize('mutation,code', [
    (lambda c: c['filters'][0].update(fields=['missing']), 'FILTER_FIELD_UNKNOWN'),
    (lambda c: c['filters'][0].update(componentIds=['missing']), 'FILTER_CONSUMER_UNKNOWN'),
    (lambda c: c['kpis'][0].pop('binding'), 'FILTER_BINDING_MISSING'),
    (lambda c: c['kpis'][0]['binding'].update(field='missing'), 'BINDING_FIELD_UNKNOWN'),
    (lambda c: c['charts'][0]['binding']['series']['values'].update(aggregate='guess'), 'BINDING_AGGREGATE_INVALID'),
])
def test_strict_filter_validation_rejects_unresolvable_bindings(mutation, code):
    config = bound_config()
    mutation(config)
    errors, _ = validate_resolved(config, strict=True)
    assert code in {error['code'] for error in errors}


def test_complete_binding_is_accepted():
    assert validate_resolved(bound_config(), strict=True)[0] == []


def test_each_component_uses_only_its_declared_filters():
    config = bound_config()
    config['filters'].append({'id': 'channel', 'key': 'channel', 'type': 'multi-select',
                             'fields': ['channel'], 'componentIds': ['sales'],
                             'options': [{'value': 'direct'}, {'value': 'partner'}]})
    config['table']['rows'][0]['channel'] = 'direct'
    config['table']['rows'][1]['channel'] = 'partner'
    result = run_runtime(f"const config = {json.dumps(config)};" + """
const app = Object.create(DashboardApp.prototype);
app.state = new StateStore(config); app.config = app.state.config;
app.state.filterValues.region = new Set(['east']);
app.state.filterValues.channel = new Set(['partner']);
console.log(JSON.stringify({kpi: app.getFilteredTableRows('revenue'),
  chart: app.getFilteredTableRows('sales'), table: app.getFilteredTableRows()}));
""")
    assert len(result['kpi']) == 1
    assert result['kpi'][0]['sales'] == 128
    assert result['chart'] == result['table'] == []


@pytest.mark.parametrize('card_type', ['mc03', 'mc06', 'mc09'])
def test_specialized_kpis_require_their_visual_data(card_type):
    config = bound_config()
    config['filters'] = []
    config['kpis'][0].pop('binding')
    config['kpis'][0]['type'] = card_type
    errors, _ = validate_resolved(config, strict=True)
    assert any(error['code'] == 'KPI_PRESENTATION_INVALID' for error in errors)


def test_sparkline_has_no_fallback_series():
    result = run_runtime("""
const app = Object.create(DashboardApp.prototype);
app.config = {kpis: [{id: 'spark', type: 'mc03', value: '0%'}]};
app.state = {chartInstances: {}}; app.getById = () => ({});
app.initKPIWidgets();
console.log(JSON.stringify(widgetOptions));
""")
    assert result == []


def test_declared_filters_match_exact_values_even_when_all_options_are_selected():
    config = bound_config()
    config['table']['rows'].append({'region': 'southeast', 'sales': 50})
    result = run_runtime(f"const config = {json.dumps(config)};" + """
const app = Object.create(DashboardApp.prototype);
app.state = new StateStore(config); app.config = app.state.config;
app.state.filterValues.region = new Set(['east', 'south']);
const multi = app.getFilteredTableRows();
app.state.filterDefs[0].type = 'select'; app.state.filterValues.region = 'east';
console.log(JSON.stringify({multi: multi.map(r => r.region), single: app.getFilteredTableRows().map(r => r.region)}));
""")
    assert result == {'multi': ['east', 'south'], 'single': ['east']}


def test_two_runtimes_do_not_mutate_the_shared_input_config():
    config = bound_config()
    result = run_runtime(f"const config = {json.dumps(config)};" + """
const left = Object.create(DashboardApp.prototype);
const right = new StateStore(config);
left.state = new StateStore(config); left.config = left.state.config;
left.getById = () => null; left.renderer = {renderKPIs() {}}; left.initKPIWidgets = () => {};
left.state.filterValues.region = new Set(['east']);
left.updateKPIsAndChartsFromFilters();
console.log(JSON.stringify([left.config.kpis[0].value, right.config.kpis[0].value, config.kpis[0].value]));
""")
    assert result == ['128 万元', '224 万元', '224 万元']


@pytest.mark.parametrize('aggregate,expected', [('sum', '224.0 万元'), ('mean', '112.0 万元'),
                                               ('min', '96.0 万元'), ('max', '128.0 万元'), ('count', '2.0 条')])
def test_aggregation_and_precision(aggregate, expected):
    config = bound_config()
    config['kpis'][0]['binding'].update(aggregate=aggregate, precision=1)
    if aggregate == 'count':
        config['kpis'][0]['unit'] = '条'
    result = run_runtime(f"const config = {json.dumps(config)};" + """
const app = Object.create(DashboardApp.prototype);
app.state = new StateStore(config); app.config = app.state.config;
app.getById = () => null; app.renderer = {renderKPIs() {}}; app.initKPIWidgets = () => {};
app.updateKPIsAndChartsFromFilters();
const all = app.config.kpis[0].value;
app.state.filterValues.region = new Set(); app.updateKPIsAndChartsFromFilters();
console.log(JSON.stringify({all, empty: app.config.kpis[0].value}));
""")
    assert result['all'] == expected
    assert result['empty'] == ({'sum': '0.0 万元', 'count': '0.0 条'}.get(aggregate, '—'))
