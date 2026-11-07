"""Layout templates and role-aware placement produce valid, distinct grids."""
import copy

import pytest

from dashboard_runtime.demo import executive_document
from dashboard_runtime.layouts import COLS, TEMPLATES, compute_layout, overlaps
from dashboard_runtime.model import DashboardError, apply_operations, validate


def rich_document():
    """The executive fixture plus more charts, KPIs and commentary."""
    doc = executive_document('layouts')
    m = doc['manifest']
    chart = m['components']['regions']
    kpi = m['components']['total']
    ops = []
    for index in range(1, 5):
        ops.append({'op': 'put_component', 'id': f'chart{index}', 'value': {**copy.deepcopy(chart), 'title': f'Chart {index}'}})
    for index in range(1, 3):
        ops.append({'op': 'put_component', 'id': f'kpi{index}', 'value': {**copy.deepcopy(kpi), 'title': f'KPI {index}'}})
    ops.append({'op': 'put_component', 'id': 'note', 'value': {'kind': 'text', 'title': 'Takeaway', 'text': 'Synthetic commentary.'}})
    order = ['total', 'load', 'passengers', 'goal', 'kpi1', 'kpi2', 'trend', 'note', 'regions', 'chart1', 'chart2', 'chart3', 'chart4', 'details']
    ops.append({'op': 'apply_layout_template', 'template': 'executive', 'order': order})
    return apply_operations(doc, ops), order


def assert_valid(layout, components):
    for breakpoint, cols in COLS.items():
        placements = layout[breakpoint]
        assert sorted(p['id'] for p in placements) == sorted(components)
        for index, item in enumerate(placements):
            assert 0 <= item['x'] and item['x'] + item['w'] <= cols and item['h'] >= 2
            assert not any(overlaps(item, other) for other in placements[:index])


@pytest.mark.parametrize('template', sorted(TEMPLATES))
def test_every_template_is_valid_on_every_breakpoint(template):
    doc, order = rich_document()
    result = apply_operations(doc, [{'op': 'apply_layout_template', 'template': template, 'order': order}])
    assert_valid(result['manifest']['layout'], result['manifest']['components'])
    assert result['manifest']['layoutTemplate'] == {'id': template, 'order': order}
    assert validate(result) is result


def test_templates_produce_distinct_desktop_compositions():
    doc, order = rich_document()
    signatures = set()
    for template in TEMPLATES:
        desktop = compute_layout(doc['manifest'], template, order)['desktop']
        signatures.add(tuple(sorted((p['id'], p['x'], p['y'], p['w'], p['h']) for p in desktop)))
    assert len(signatures) == len(TEMPLATES)
    focus = {p['id']: p for p in compute_layout(doc['manifest'], 'focus', order)['desktop']}
    assert focus['trend']['w'] == 12 and focus['trend']['h'] > focus['regions']['h']
    sidebar = {p['id']: p for p in compute_layout(doc['manifest'], 'sidebar', order)['desktop']}
    assert {sidebar[key]['x'] for key in ('total', 'load', 'kpi1')} == {0} and sidebar['trend']['x'] == 3
    narrative = {p['id']: p for p in compute_layout(doc['manifest'], 'narrative', order)['desktop']}
    assert (narrative['trend']['w'], narrative['note']['x']) == (8, 8)
    scorecard = compute_layout(doc['manifest'], 'scorecard', order)
    assert sum(1 for p in scorecard['desktop'] if p['y'] == 0 and p['id'] in order[:6]) == 6
    assert {p['w'] for p in scorecard['mobile'] if p['id'] in order[:6]} == {2}


def test_template_is_applied_after_components_created_in_the_same_batch():
    doc = executive_document('batch')
    chart = copy.deepcopy(doc['manifest']['components']['regions'])
    result = apply_operations(doc, [
        {'op': 'apply_layout_template', 'template': 'grid3'},
        {'op': 'put_component', 'id': 'late', 'value': {**chart, 'title': 'Created after the template op'}},
    ])
    assert any(p['id'] == 'late' for p in result['manifest']['layout']['desktop'])
    assert_valid(result['manifest']['layout'], result['manifest']['components'])


def test_saved_template_reflows_and_manual_layout_replaces_it():
    doc, order = rich_document()
    chart = copy.deepcopy(doc['manifest']['components']['regions'])
    added = apply_operations(doc, [{'op': 'put_component', 'id': 'extra', 'value': {**chart, 'title': 'Extra'}}])
    assert added['manifest']['layout'] == compute_layout(added['manifest'], 'executive', order)
    removed = apply_operations(added, [{'op': 'remove_component', 'id': 'chart4'}])
    assert 'chart4' not in removed['manifest']['layoutTemplate']['order']
    assert_valid(removed['manifest']['layout'], removed['manifest']['components'])
    desktop = copy.deepcopy(removed['manifest']['layout']['desktop'])
    manual = apply_operations(removed, [{'op': 'set_layout', 'breakpoint': 'desktop', 'value': desktop}])
    assert 'layoutTemplate' not in manual['manifest']
    again = apply_operations(manual, [{'op': 'put_component', 'id': 'late', 'value': {**chart, 'title': 'Late'}}])
    assert [p for p in again['manifest']['layout']['desktop'] if p['id'] != 'late'] == desktop


def test_new_components_pack_by_role_instead_of_stacking_full_width():
    doc = executive_document('auto')
    m = doc['manifest']
    kpi, chart = copy.deepcopy(m['components']['total']), copy.deepcopy(m['components']['regions'])
    base = apply_operations(doc, [{'op': 'set_layout', 'breakpoint': 'desktop', 'value': [
        {'id': 'total', 'x': 0, 'y': 0, 'w': 3, 'h': 4}, {'id': 'load', 'x': 3, 'y': 0, 'w': 3, 'h': 4},
        {'id': 'passengers', 'x': 0, 'y': 4, 'w': 3, 'h': 4}, {'id': 'goal', 'x': 3, 'y': 4, 'w': 3, 'h': 4},
        {'id': 'trend', 'x': 6, 'y': 0, 'w': 6, 'h': 16}, {'id': 'regions', 'x': 0, 'y': 8, 'w': 6, 'h': 8},
        {'id': 'details', 'x': 0, 'y': 16, 'w': 12, 'h': 8}]}])
    grown = apply_operations(base, [
        {'op': 'put_component', 'id': 'k5', 'value': {**kpi, 'title': 'K5'}},
        {'op': 'put_component', 'id': 'k6', 'value': {**kpi, 'title': 'K6'}},
        {'op': 'put_component', 'id': 'c3', 'value': {**chart, 'title': 'C3'}},
        {'op': 'put_component', 'id': 'c4', 'value': {**chart, 'title': 'C4'}},
    ])
    desktop = {p['id']: p for p in grown['manifest']['layout']['desktop']}
    # KPIs start a KPI row (never beside the tall chart) and fill it; charts pair up.
    assert desktop['k5']['y'] == desktop['k6']['y'] == 24 and (desktop['k5']['x'], desktop['k6']['x']) == (0, 3)
    assert desktop['c3']['w'] == 6 and desktop['c4']['y'] == desktop['c3']['y'] and desktop['c4']['x'] == 6
    assert_valid(grown['manifest']['layout'], grown['manifest']['components'])


def test_invalid_templates_and_orders_are_rejected():
    doc = executive_document('bad')
    with pytest.raises(DashboardError) as error:
        apply_operations(doc, [{'op': 'apply_layout_template', 'template': 'carousel'}])
    assert error.value.code == 'UNKNOWN_LAYOUT'
    with pytest.raises(DashboardError, match='missing components'):
        apply_operations(doc, [{'op': 'apply_layout_template', 'template': 'bento', 'order': ['ghost']}])
    with pytest.raises(DashboardError, match='layoutTemplate'):
        broken = copy.deepcopy(doc)
        broken['manifest']['layoutTemplate'] = {'id': 'carousel'}
        validate(broken)
