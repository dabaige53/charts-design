"""Read-only, packaged generation cases. Never insert example data implicitly."""
from copy import deepcopy
from .demo import executive_document, operations_document, report_document
from .model import require

CASES = {
    'executive-dashboard': {'track': 'dashboard', 'title': 'Revenue and capacity dashboard',
        'description': 'Synthetic mc01–mc04 cards, bound monthly/quarterly t06 chart, regional comparison, detail table and explicit region/date filters.',
        'skill': 'skills/executive-charts/SKILL.md'},
    'operations-scorecard': {'track': 'dashboard', 'title': '航空运营指标墙 · 收入、运力与目标',
        'description': 'Contrasting composition on the same synthetic data: scorecard layout template, mc16 hero, mc11 ring, mc13 bullet, mc14 period comparison, mc12 mini bars and mc05 gauge, with c02/c03/t01 charts. All bound values recompute under filters.',
        'skill': 'skills/executive-charts/SKILL.md'},
    'academic-report': {'track': 'report', 'title': '季度收入变化与区域结构的描述性分析',
        'description': 'Approved academic reading master: authored title, abstract, methods, analysis, inline figures, conclusions and limitations.',
        'skill': 'skills/analytical-reports/SKILL.md'},
}

def case_operations(doc):
    """Portable declarations for a single atomic patch on a fresh dashboard."""
    m = doc['manifest']
    ops = [{'op': 'set_title', 'value': m['title']}]
    if 'meta' in m:
        ops.append({'op': 'set_meta', 'value': deepcopy(m['meta'])})
    for key, value in m['sources'].items():
        ops.append({'op':'put_source', 'id':key, 'value':deepcopy(value)})
    for key, value in m['datasets'].items():
        ops.append({'op':'put_dataset', 'id':key, 'meta':deepcopy(value), 'rows':deepcopy(doc['snapshot']['datasets'][key])})
    for collection, op in [('metrics','put_metric'), ('components','put_component')]:
        ops.extend({'op':op,'id':key,'value':deepcopy(value)} for key,value in m[collection].items())
    ops += [{'op':'set_filters','value':deepcopy(m['filters'])}, {'op':'set_status','value':'fixture'}]
    if m.get('layoutTemplate'):
        # A named composition, not hand-written coordinates; it is applied after the batch.
        ops.append({'op':'apply_layout_template','template':m['layoutTemplate']['id'], **({'order':list(m['layoutTemplate']['order'])} if m['layoutTemplate'].get('order') else {})})
    else:
        ops.extend({'op':'set_layout','breakpoint':key,'value':deepcopy(value)} for key,value in m['layout'].items())
    if m.get('report', {}).get('markdown') is not None:
        ops.append({'op':'set_report_markdown','value':m['report']['markdown']})
    ops.append({'op':'set_view_mode','value':m.get('viewMode','dashboard')})
    return ops

def generation_examples(case_id=None):
    if case_id is None:
        return {'cases':[{'id':key, **value, 'uri':f'charts://examples/{key}'} for key,value in CASES.items()],
                'presentationStatus':'unavailable',
                'policy':'Examples are synthetic references, not user data. Select a case explicitly, replace data and recompute every narrative claim before real use.',
                'workflow':['chart_recommend(intent, data shape)', 'chart_declarations(code)', 'layout_templates', 'generation_examples(caseId)', 'dashboard_create', 'dashboard_edit_begin', 'dashboard_patch(expectedRevision, operations incl. apply_layout_template)', 'dashboard_edit_finish', 'dashboard_get'],
                'variety':'The two dashboard cases share data but differ in layout template, KPI shapes and chart codes. Choose per question with chart_recommend and the kpiGuide; do not reuse one composition for every dashboard.'}
    require(case_id in CASES, 'Unknown generation case', 'UNKNOWN_EXAMPLE')
    doc = {'academic-report': report_document, 'operations-scorecard': operations_document}.get(case_id, executive_document)('example')
    return {'id':case_id, **CASES[case_id], 'synthetic':True, 'operations':case_operations(doc),
            'markdown':doc['manifest'].get('report',{}).get('markdown'),
            'adaptationRules':['Keep stable component IDs and chart fences in sync.',
                'Use the report master structure and restrained reading style, but include abstract/keywords only when authored.',
                'Declare provenance, units, aggregation and uncertainty; do not reuse synthetic findings with new data.',
                'Use chart fences for declarations already registered as components, not executable JavaScript.',
                'Validate and inspect saved declarations with dashboard_get; UI rendering is unavailable during reconstruction. Narrative is not automatically recalculated by filters.']}
