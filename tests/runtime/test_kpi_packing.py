"""Deterministic geometry tests; these do not assert visual browser fidelity."""
import copy
import itertools
import pytest
from dashboard_runtime.layouts import COLS, TEMPLATES, compute_layout, overlaps, weighted_rows, kpi_height, auto_place


def manifest(count, mixed=False):
    components = {}
    for i in range(count):
        c = {'kind': 'kpi', 'title': 'Revenue', 'presentation': {'type': f'mc{(i % 16) + 1:02}' if mixed else 'mc01'}}
        if mixed and i % 7 == 0:
            c['layoutPriority'] = 'primary'
        components[f'k{i}'] = c
    return {'components': components}


# @wu-test type=behavior | scope=test_kpi_packing | protects=all counts remain valid
@pytest.mark.parametrize('count', [0, 1, 2, 3, 4, 5, 7, 8, 11, 12, 19, 20, 21, 40, 100])
@pytest.mark.parametrize('template', list(TEMPLATES))
@pytest.mark.parametrize('mixed', [False, True])
def test_all_counts_remain_valid(count, template, mixed):
    m = manifest(count, mixed)
    original = copy.deepcopy(m)
    result = compute_layout(m, template)
    assert m == original
    for bp, columns in COLS.items():
        placements = result[bp]
        assert [p['id'] for p in placements] == list(m['components'])
        for index, p in enumerate(placements):
            assert all(type(p[key]) is int for key in ('x', 'y', 'w', 'h'))
            assert 0 <= p['x'] < columns and p['x'] + p['w'] <= columns
            assert p['h'] >= 4 and p['w'] >= 1
            assert not any(overlaps(p, q) for q in placements[:index])
        for y in {p['y'] for p in placements}:
            assert sum(p['w'] for p in placements if p['y'] == y) == columns


# @wu-test type=behavior | scope=test_kpi_packing | protects=readable density across breakpoints
@pytest.mark.parametrize('count', [1, 4, 8, 12, 20])
def test_readable_density_across_breakpoints(count):
    result = compute_layout(manifest(count), 'scorecard')
    for bp, cap in [('desktop', 4), ('tablet', 2), ('mobile', 1)]:
        for y in {p['y'] for p in result[bp]}:
            assert len([p for p in result[bp] if p['y'] == y]) <= cap


# @wu-test type=behavior | scope=test_kpi_packing | protects=priority allocates space without reordering
def test_priority_allocates_space_without_reordering():
    m = manifest(3);m['components']['k0']['layoutPriority'] = 'primary'
    row = compute_layout(m, 'executive')['desktop']
    assert [p['id'] for p in row] == ['k0', 'k1', 'k2']
    assert [p['w'] for p in row] == [6, 3, 3]
    assert all(p['h'] == 5 for p in row)
    reverse = compute_layout(m, 'executive', ['k2', 'k1', 'k0'])['desktop']
    assert [p['id'] for p in reverse] == ['k2', 'k1', 'k0']


# @wu-test type=behavior | scope=test_kpi_packing | protects=weighted packing balances wide cards
def test_weighted_packing_balances_wide_cards():
    keys = list('abcde');weights = dict(zip(keys, [2, 1, 1, 1, 1]))
    rows = weighted_rows(keys, weights, 4)
    assert [sum(w for _, w in row) for row in rows] == [3, 3]
    assert [key for row in rows for key, _ in row] == keys


# @wu-test type=behavior | scope=test_kpi_packing | protects=weighted packing matches brute force optimum
def test_weighted_packing_matches_brute_force_optimum():
    for weights_tuple in itertools.product([1, 2], repeat=7):
        keys = list(range(7));weights = dict(zip(keys, weights_tuple))
        options = []
        for cuts in itertools.product([False, True], repeat=6):
            totals, total = [], weights_tuple[0]
            for cut, weight in zip(cuts, weights_tuple[1:]):
                if cut:
                    totals.append(total);total = weight
                else:
                    total += weight
            totals.append(total)
            if max(totals) <= 4:
                options.append((len(totals), sum(x*x for x in totals)))
        rows = weighted_rows(keys, weights, 4)
        sums = [sum(w for _, w in row) for row in rows]
        assert (len(rows), sum(x*x for x in sums)) == min(options)


# @wu-test type=behavior | scope=test_kpi_packing | protects=long content gets more height not smaller text
def test_long_content_gets_more_height_not_smaller_text():
    c = manifest(1)['components']['k0']
    assert kpi_height(c) == 4
    c['title'] = 'Long name ' * 10
    assert kpi_height(c) == 5


# @wu-test type=behavior | scope=test_kpi_packing | protects=manual layout is not reflowed by append
def test_manual_layout_is_not_reflowed_by_append():
    m = manifest(1);m['layout'] = compute_layout(m, 'executive')
    previous = copy.deepcopy(m['layout'])
    auto_place(m, 'next', {'kind': 'kpi', 'presentation': {'type': 'mc01'}})
    for bp in COLS:
        assert m['layout'][bp][:-1] == previous[bp]
        assert not overlaps(m['layout'][bp][-1], m['layout'][bp][0])


# @wu-test type=behavior | scope=test_kpi_packing | protects=body and tables preserve existing compositions
@pytest.mark.parametrize('template', list(TEMPLATES))
def test_body_and_tables_preserve_existing_compositions(template):
    m = manifest(12, True)
    m['components'].update({'chart1': {'kind': 'chart'}, 'narrative': {'kind': 'text'}, 'chart2': {'kind': 'chart'}, 'details': {'kind': 'table'}})
    for bp, placements in compute_layout(m, template).items():
        assert {p['id'] for p in placements} == set(m['components'])
        for index, p in enumerate(placements):
            assert not any(overlaps(p, q) for q in placements[:index])
        assert placements[-1]['id'] == 'details' and placements[-1]['w'] == COLS[bp]
