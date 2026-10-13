"""Read-only, packaged generation cases. Never insert example data implicitly."""
from copy import deepcopy
from .demo import executive_document, report_document
from .model import require

CASES = {
    'executive-dashboard': {'track': 'dashboard', 'title': 'Revenue and capacity dashboard',
        'description': 'Synthetic mc01–mc04 cards, bound monthly/quarterly t06 chart, regional comparison, detail table and explicit region/date filters.',
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
    ops.extend({'op':'set_layout','breakpoint':key,'value':deepcopy(value)} for key,value in m['layout'].items())
    ops += [{'op':'set_filters','value':deepcopy(m['filters'])}, {'op':'set_status','value':'fixture'}]
    if m.get('report', {}).get('markdown') is not None:
        ops.append({'op':'set_report_markdown','value':m['report']['markdown']})
    ops.append({'op':'set_view_mode','value':m.get('viewMode','dashboard')})
    return ops

def generation_examples(case_id=None):
    if case_id is None:
        return {'cases':[{'id':key, **value, 'uri':f'charts://examples/{key}'} for key,value in CASES.items()],
                'policy':'Examples are synthetic references, not user data. Select a case explicitly, replace data and recompute every narrative claim before real use.',
                'workflow':['chart_declarations', 'generation_examples(caseId)', 'dashboard_create', 'dashboard_patch(expectedRevision, operations)', 'dashboard_validate', 'dashboard_preview']}
    require(case_id in CASES, 'Unknown generation case', 'UNKNOWN_EXAMPLE')
    doc = (report_document if case_id == 'academic-report' else executive_document)('example')
    return {'id':case_id, **CASES[case_id], 'synthetic':True, 'operations':case_operations(doc),
            'markdown':doc['manifest'].get('report',{}).get('markdown'),
            'adaptationRules':['Keep stable component IDs and chart fences in sync.',
                'Use the report master structure and restrained reading style, but include abstract/keywords only when authored.',
                'Declare provenance, units, aggregation and uncertainty; do not reuse synthetic findings with new data.',
                'Use chart fences for declarations already registered as components, not executable JavaScript.',
                'Validate then render and inspect the output. Narrative is not automatically recalculated by filters.']}
