"""Markdown reports reuse v2 components, revisions and the export boundary."""
import copy
import json
import re
import subprocess
import sys

import pytest

from dashboard_runtime import assets
from dashboard_runtime.contract import CONTRACT
from dashboard_runtime.demo import document, report_document
from dashboard_runtime.model import (
    DashboardError, MAX_REPORT_CAPTION, MAX_REPORT_MARKDOWN, MAX_REPORT_SOURCE,
    apply_operations, new_document,
    report_chart_references, report_markdown, validate,
)
from dashboard_runtime.service import Service


def legacy_report(*keys, subtitle='A personal analysis'):
    return {'subtitle': subtitle, 'blocks': [{'id': key, 'componentId': key} for key in keys]}


def fence(key, **metadata):
    return '```chart\n' + json.dumps({'componentId': key, **metadata}, ensure_ascii=False) + '\n```'


def patch_markdown(doc, source):
    return apply_operations(doc, [{'op': 'set_report_markdown', 'value': source}])


def patch_legacy(doc, value):
    return apply_operations(doc, [{'op': 'set_report', 'value': value}])


def test_old_documents_remain_valid_and_unchanged():
    doc = document()
    before = copy.deepcopy(doc)
    assert validate(doc) is doc
    assert doc == before
    assert 'viewMode' not in doc['manifest'] and 'report' not in doc['manifest']


def test_mode_initializes_reading_order_without_changing_grid_or_components():
    doc = document()
    placements = doc['manifest']['layout']['desktop']
    placements[0]['x'], placements[1]['x'] = placements[1]['x'], placements[0]['x']
    changed = apply_operations(doc, [{'op': 'set_view_mode', 'value': 'report'}])
    assert changed['manifest']['viewMode'] == 'report'
    assert report_chart_references(changed['manifest']['report']['markdown']) == ['load', 'total', 'trend', 'regions', 'details']
    for key in ('layout', 'datasets', 'metrics', 'sources', 'filters'):
        assert changed['manifest'][key] == doc['manifest'][key]
    assert changed['snapshot'] == doc['snapshot']
    assert 'report' not in doc['manifest']


def test_canonical_source_survives_mode_switches_and_accepts_empty_report():
    for source in ('', '# Analysis\n\n**Finding.**\n\n' + fence('regions') + '\n\n' + fence('trend')):
        doc = patch_markdown(document(), source)
        assert 'viewMode' not in doc['manifest']
        for mode in ('report', 'dashboard', 'report'):
            doc = apply_operations(doc, [{'op': 'set_view_mode', 'value': mode}])
            assert doc['manifest']['report'] == {'markdown': source}


def test_absent_report_metadata_and_legacy_empty_report_are_valid():
    doc = new_document('empty', 'Empty')
    doc['manifest']['viewMode'] = 'report'
    assert validate(doc)
    assert patch_legacy(doc, legacy_report())['manifest']['report']['blocks'] == []


@pytest.mark.parametrize('value', [None, 'slides', '', 0, {}, []])
def test_invalid_view_mode_is_rejected(value):
    with pytest.raises(DashboardError, match='Unknown view mode'):
        apply_operations(document(), [{'op': 'set_view_mode', 'value': value}])
    doc = document()
    doc['manifest']['viewMode'] = value
    with pytest.raises(DashboardError, match='Unknown view mode'):
        validate(doc)


@pytest.mark.parametrize('source', [None, 0, {}, [], 'x' * (MAX_REPORT_MARKDOWN + 1)])
def test_markdown_type_and_limit(source):
    with pytest.raises(DashboardError, match='markdown must contain'):
        patch_markdown(document(), source)
    doc = document()
    doc['manifest']['report'] = {'markdown': source}
    with pytest.raises(DashboardError, match='markdown must contain'):
        validate(doc)


def test_markdown_accepts_maximum_characters_and_literal_code():
    assert validate(patch_markdown(document(), '文' * MAX_REPORT_MARKDOWN))
    source = '''# Title

<script>not executed here</script>

````markdown
```chart
{"componentId":"missing"}
```
````

```python
print("ordinary code")
```
'''
    assert report_chart_references(source) == []
    assert patch_markdown(document(), source)['manifest']['report']['markdown'] == source


@pytest.mark.parametrize('source', [
    '```chart\n', '```chart\n{}\n```', '```chart\n[]\n```',
    '```chart\nnot JSON\n```', '```chart\n{"componentId":',
    '```chart\n{"componentId":"trend",}\n```',
    '```chart\n{"componentId":"trend","script":"alert(1)"}\n```',
    '```chart\n{"componentId":"trend","componentId":"regions"}\n```',
    '```chart\n{"componentId":null}\n```',
    '```chart\n{"componentId":["trend"]}\n```',
    '```chart\n{"componentId":"bad id"}\n```',
    '```chart\n{"componentId":"missing"}\n```',
    '````chart\n{"componentId":"trend"}\n```',
    '~~~chart\n{"componentId":"trend"}\n```',
])
def test_invalid_chart_fences_cannot_persist(source):
    with pytest.raises(DashboardError):
        patch_markdown(document(), source)
    doc = document()
    doc['manifest']['report'] = {'markdown': source}
    with pytest.raises(DashboardError):
        validate(doc)


def test_chart_fences_require_non_text_references_and_allow_repetition():
    doc = apply_operations(document(), [{'op': 'put_component', 'id': 'note', 'value': {'kind': 'text', 'title': 'Note', 'text': 'Plain'}}])
    with pytest.raises(DashboardError, match='non-text'):
        patch_markdown(doc, fence('note'))
    source = '\n\n'.join(fence(key) for key in ('trend', 'total', 'details', 'trend'))
    assert report_chart_references(patch_markdown(doc, source)['manifest']['report']['markdown']) == ['trend', 'total', 'details', 'trend']


@pytest.mark.parametrize('metadata', [
    {}, {'caption': ''}, {'source': ''},
    {'caption': '月度收入变化', 'source': '数据来源：内置合成快照。'},
    {'caption': '文' * MAX_REPORT_CAPTION, 'source': '源' * MAX_REPORT_SOURCE},
    {'caption': '<script>alert(1)</script>', 'source': '**plain metadata**\nnot code'},
])
def test_optional_figure_metadata_is_bounded_plain_text_and_preserves_exact_source(metadata):
    source = '[图](#fig-trend)\n\n' + fence('trend', **metadata) + '\n\n' + fence('trend')
    changed = patch_markdown(document(), source)
    assert report_chart_references(source, changed['manifest']['components']) == ['trend', 'trend']
    assert changed['manifest']['report']['markdown'] == source
    assert validate(changed)


@pytest.mark.parametrize('metadata', [
    {'caption': None}, {'caption': 1}, {'caption': []}, {'caption': {}}, {'caption': False},
    {'source': None}, {'source': 1}, {'source': []}, {'source': {}}, {'source': False},
    {'caption': '文' * (MAX_REPORT_CAPTION + 1)},
    {'source': '源' * (MAX_REPORT_SOURCE + 1)},
    {'caption': 'valid', 'source': 'valid', 'figureId': 'fig-one'},
])
def test_invalid_figure_metadata_rejects_mutation_and_import(metadata):
    doc = document()
    before = copy.deepcopy(doc)
    source = fence('trend', **metadata)
    with pytest.raises(DashboardError):
        patch_markdown(doc, source)
    assert doc == before
    doc['manifest']['report'] = {'markdown': source}
    with pytest.raises(DashboardError):
        validate(doc)


@pytest.mark.parametrize('payload', [
    '{"caption":"Missing component"}',
    '{"componentId":"trend","caption":"one","caption":"two"}',
    '{"componentId":"trend","source":"one","source":"two"}',
    '{"componentId":"trend","caption":"valid","unknown":"bad"}',
])
def test_metadata_does_not_relax_required_or_unique_chart_keys(payload):
    with pytest.raises(DashboardError):
        patch_markdown(document(), '```chart\n' + payload + '\n```')


@pytest.mark.parametrize('source', [
    '~~~chart\n{"componentId":"trend"}\n~~~~',
    '   ```chart \n{"componentId":"trend"}\n   ```\t',
    '````chart\n{"componentId":"trend"}\n`````',
    '```chart\r\n{"componentId":"trend"}\r\n```',
])
def test_supported_fence_variants(source):
    assert report_chart_references(source, document()['manifest']['components']) == ['trend']


def test_non_chart_languages_and_indented_examples_are_not_references():
    assert report_chart_references('```javascript\nanything\n```') == []
    assert report_chart_references('```Chart\nanything\n```') == []
    assert report_chart_references('    ```chart\n    anything\n    ```') == []


def test_new_component_does_not_insert_source_and_updates_preserve_source():
    source = '# Draft\n\n' + fence('trend')
    doc = patch_markdown(document(), source)
    doc = apply_operations(doc, [
        {'op': 'put_component', 'id': 'trend', 'value': {**doc['manifest']['components']['trend'], 'title': 'Revised'}},
        {'op': 'put_component', 'id': 'note', 'value': {'kind': 'text', 'title': '', 'text': 'Unlisted'}},
    ])
    assert doc['manifest']['report'] == {'markdown': source}
    assert all(any(p['id'] == 'note' for p in layout) for layout in doc['manifest']['layout'].values())


def test_referenced_component_deletion_is_actionable_and_atomic():
    doc = patch_markdown(document(), fence('trend'))
    before = copy.deepcopy(doc)
    with pytest.raises(DashboardError, match='remove its chart fence') as error:
        apply_operations(doc, [{'op': 'remove_component', 'id': 'trend'}])
    assert error.value.code == 'REPORT_COMPONENT_REFERENCED'
    assert doc == before
    changed = apply_operations(doc, [
        {'op': 'set_report_markdown', 'value': '# Kept my prose'},
        {'op': 'remove_component', 'id': 'trend'},
    ])
    assert changed['manifest']['report']['markdown'] == '# Kept my prose'
    assert 'trend' not in changed['manifest']['components']
    assert all(p['id'] != 'trend' for layout in changed['manifest']['layout'].values() for p in layout)
    assert 'trend' not in changed['manifest']['filters'][0]['componentIds']


def test_references_can_precede_creation_in_atomic_batch():
    doc = document()
    updated = apply_operations(doc, [
        {'op': 'set_report_markdown', 'value': fence('new-chart')},
        {'op': 'put_component', 'id': 'new-chart', 'value': doc['manifest']['components']['trend']},
        {'op': 'set_view_mode', 'value': 'report'},
    ])
    assert updated['manifest']['report']['markdown'] == fence('new-chart')


def test_changing_referenced_chart_to_text_is_rejected():
    doc = patch_markdown(document(), fence('trend'))
    with pytest.raises(DashboardError, match='non-text'):
        apply_operations(doc, [{'op': 'put_component', 'id': 'trend', 'value': {'kind': 'text', 'title': '', 'text': 'Replacement'}}])


def test_legacy_migration_is_safe_non_mutating_and_preserves_metadata():
    doc = apply_operations(document(), [
        {'op': 'set_title', 'value': 'Title <script>'},
        {'op': 'put_component', 'id': 'note', 'value': {'kind': 'text', 'title': '# Plain', 'subtitle': 'Narrative subtitle <img>', 'text': '```chart\n{"componentId":"missing"}\n```\n<script>alert(1)</script> **plain**'}},
        {'op': 'set_report', 'value': legacy_report('note', 'trend', subtitle='An <img> subtitle')},
    ])
    original = copy.deepcopy(doc)
    source = report_markdown(doc['manifest'])
    assert doc == original
    assert source.startswith('# Title \\<script\\>')
    assert 'Narrative subtitle \\<img\\>' in source
    assert '## \\# Plain' in source and '\\*\\*plain\\*\\*' in source
    assert report_chart_references(source) == ['trend']
    migrated = apply_operations(doc, [{'op': 'set_view_mode', 'value': 'report'}])
    assert migrated['manifest']['report'] == {**doc['manifest']['report'], 'markdown': source}
    assert migrated['manifest']['components'] == doc['manifest']['components']


def test_legacy_migration_waits_for_later_references_in_batch():
    doc = apply_operations(document(), [
        {'op': 'set_report', 'value': legacy_report('new-note', 'trend')},
        {'op': 'set_view_mode', 'value': 'report'},
        {'op': 'put_component', 'id': 'new-note', 'value': {'kind': 'text', 'title': 'Finding', 'text': 'Authored finding'}},
    ])
    assert 'Authored finding' in doc['manifest']['report']['markdown']
    assert report_chart_references(doc['manifest']['report']['markdown']) == ['trend']


def test_canonical_source_overrides_stale_legacy_references():
    doc = patch_legacy(document(), legacy_report('trend', 'regions'))
    doc = patch_markdown(doc, '# Independent source')
    doc = apply_operations(doc, [{'op': 'remove_component', 'id': 'trend'}])
    assert doc['manifest']['report']['blocks'] == legacy_report('trend', 'regions')['blocks']
    assert report_markdown(doc['manifest']) == '# Independent source'
    assert validate(doc)


@pytest.mark.parametrize('value', [
    None, [], {}, {'subtitle': '', 'blocks': {}}, {'subtitle': None, 'blocks': []},
    legacy_report(subtitle='x' * 1001), {'subtitle': '', 'blocks': [None]},
    {'subtitle': '', 'blocks': [{'id': 'bad id', 'componentId': 'trend'}]},
    {'subtitle': '', 'blocks': [{'id': 'x' * 81, 'componentId': 'trend'}]},
    {'subtitle': '', 'blocks': [{'id': 'section', 'componentId': ['trend']}]},
    {'subtitle': '', 'blocks': [{'id': 'section', 'componentId': 'missing'}]},
    {'subtitle': '', 'blocks': [{'id': 'section', 'componentId': 'trend'}, {'id': 'section', 'componentId': 'regions'}]},
    {'subtitle': '', 'blocks': [{'id': 'one', 'componentId': 'trend'}, {'id': 'two', 'componentId': 'trend'}]},
    legacy_report(*[f'block-{n}' for n in range(101)]),
])
def test_invalid_legacy_report_is_rejected(value):
    with pytest.raises(DashboardError):
        patch_legacy(document(), value)
    doc = document()
    doc['manifest']['report'] = value
    with pytest.raises(DashboardError):
        validate(doc)


def test_legacy_set_report_still_replaces_and_manages_blocks():
    doc = patch_markdown(document(), '# Modern')
    doc = patch_legacy(doc, legacy_report('trend'))
    assert 'markdown' not in doc['manifest']['report']
    doc = apply_operations(doc, [{'op': 'put_component', 'id': 'note', 'value': {'kind': 'text', 'title': '', 'text': 'Legacy'}}])
    assert doc['manifest']['report'] == legacy_report('trend', 'note')
    doc = apply_operations(doc, [{'op': 'remove_component', 'id': 'trend'}])
    assert doc['manifest']['report'] == legacy_report('note')


def test_legacy_report_limits_and_block_id_collisions_remain_supported():
    doc = patch_legacy(new_document('bounded', 'Bounded'), legacy_report(subtitle='x' * 1000))
    doc = apply_operations(doc, [{'op': 'put_component', 'id': f'note-{n}', 'value': {'kind': 'text', 'title': '', 'text': ''}} for n in range(100)])
    assert len(doc['manifest']['report']['blocks']) == 100
    key = 'n' * 80
    doc = patch_legacy(document(), {'subtitle': '', 'blocks': [{'id': key, 'componentId': 'trend'}, {'id': key[:78] + '-2', 'componentId': 'regions'}]})
    doc = apply_operations(doc, [{'op': 'put_component', 'id': key, 'value': {'kind': 'text', 'title': '', 'text': ''}}])
    assert doc['manifest']['report']['blocks'][-1] == {'id': key[:78] + '-3', 'componentId': key}


def test_persistence_atomic_rollback_conflict_and_restore(tmp_path):
    service = Service(tmp_path)
    initial = service.store.create('analysis', 'Analysis', document())
    for invalid in (fence('missing'), '```chart\nnot json\n```',
                    fence('trend', caption='文' * (MAX_REPORT_CAPTION + 1)),
                    fence('trend', source=None)):
        with pytest.raises(DashboardError):
            service.call('dashboard_patch', {'dashboardId': 'analysis', 'expectedRevision': 1, 'operations': [
                {'op': 'set_title', 'value': 'Must not persist'},
                {'op': 'set_report_markdown', 'value': invalid},
            ]})
        assert service.store.get('analysis') == initial
        assert len(service.store.history('analysis')) == 1
    source = '# Saved\n\nSee [图](#fig-trend).\n\n' + fence('trend', caption='月度收入', source='合成快照') + '\n\nAfter.'
    saved = service.call('dashboard_patch', {'dashboardId': 'analysis', 'expectedRevision': 1, 'operations': [
        {'op': 'set_report_markdown', 'value': source}, {'op': 'set_view_mode', 'value': 'report'},
    ]})['document']
    assert Service(tmp_path).store.get('analysis') == saved
    with pytest.raises(DashboardError) as error:
        service.store.mutate('analysis', 1, [{'op': 'set_view_mode', 'value': 'dashboard'}])
    assert error.value.code == 'REVISION_CONFLICT'
    restored = service.store.mutate('analysis', 2, restore_revision=1)
    assert restored['manifest'] == initial['manifest']
    assert service.store.mutate('analysis', 3, restore_revision=2)['manifest'] == saved['manifest']


def test_demo_is_markdown_document_with_two_shared_charts_and_synthetic_label():
    doc = report_document()
    assert validate(doc)
    m = doc['manifest']
    assert doc['snapshot']['status'] == 'fixture' and m['viewMode'] == 'report'
    source = m['report']['markdown']
    assert report_chart_references(source) == ['trend', 'regions']
    assert source.startswith('# 季度收入变化与区域结构的描述性分析\n\n*——基于 2026 年 7—9 月的示例数据*')
    assert all(marker in source for marker in ('**摘要：**', '**关键词：**', '## 数据与分析方法', '## 月度收入变化', '## 区域收入结构', '## 结论与局限', '合成', '筛选条件不会自动改写'))
    assert source.count('[图](#fig-trend)') == 2 and '[图](#fig-regions)' in source
    assert not re.search(r'^## \d', source, flags=re.MULTILINE)
    figures = [json.loads(block) for block in re.findall(r'```chart\n(.*?)\n```', source, flags=re.DOTALL)]
    assert all(set(figure) == {'componentId', 'caption', 'source'} for figure in figures)
    assert all(figure['caption'] and '合成' in figure['source'] for figure in figures)
    dashboard = document()
    for key in ('layout', 'datasets', 'metrics', 'sources', 'filters'):
        assert m[key] == dashboard['manifest'][key]
    assert [(m['components'][key]['kind'], m['components'][key]['config']['code']) for key in ('trend', 'regions')] == [('legacy', 't01'), ('legacy', 'c01')]
    assert doc['snapshot']['datasets'] == dashboard['snapshot']['datasets']
    assert 'blocks' not in m['report']


def test_cli_report_init_demo_json_export_and_import(tmp_path):
    def run(*args):
        return subprocess.run([sys.executable, '-m', 'dashboard_runtime', '--root', str(tmp_path / 'cli'), *args], text=True, capture_output=True)

    empty = run('init', 'empty', '--mode', 'report', '--title', 'My analysis')
    assert empty.returncode == 0, empty.stderr
    doc = json.loads(empty.stdout)['document']
    assert doc['revision'] == 1 and doc['manifest']['title'] == 'My analysis'
    assert doc['manifest']['report'] == {'markdown': '# My analysis\n'}
    assert doc['manifest']['components'] == {} and doc['snapshot']['datasets'] == {}
    demo = run('init', 'analysis', '--demo', '--mode', 'report')
    assert demo.returncode == 0, demo.stderr
    original = json.loads(demo.stdout)['document']
    path = tmp_path / 'report.json'
    assert run('export', 'analysis', '--format', 'json', '--output', str(path)).returncode == 0
    imported = run('import', 'copy', '--file', str(path))
    assert imported.returncode == 0, imported.stderr
    assert json.loads(imported.stdout)['document']['manifest'] == original['manifest']
    assert json.loads(run('validate', 'copy').stdout) == {'valid': True}
    old = run('init', 'old')
    assert 'viewMode' not in json.loads(old.stdout)['document']['manifest']


def test_offline_export_escapes_source_and_single_component_resets_report(tmp_path, monkeypatch):
    (tmp_path / 'app.js').write_text('window.loaded=true;')
    (tmp_path / 'app.css').write_text('body{}')
    monkeypatch.setattr(assets, 'DIST', tmp_path)
    payload = '</script><script>alert(1)</script>'
    doc = patch_markdown(report_document(), '# Literal content\n' + payload + '\n\n' + fence('trend'))
    html = assets.export_document(doc)
    assert payload not in html
    match = re.search(r'window.__DASHBOARD_BOOT__=(.*?);</script>', html)
    assert match is not None
    boot = json.loads(match.group(1))
    assert boot['mode'] == 'offline' and boot['document'] == doc
    html = assets.export_component(doc, 'trend')
    match = re.search(r'window.__DASHBOARD_BOOT__=(.*?);</script>', html)
    assert match is not None
    single = json.loads(match.group(1))['document']
    assert set(single['manifest']['components']) == {'trend'}
    assert single['manifest']['viewMode'] == 'dashboard' and 'report' not in single['manifest']
    assert validate(single)


def test_report_operations_are_discoverable():
    assert CONTRACT['schemaVersion'] == 2
    assert {'set_report_markdown', 'set_report', 'set_view_mode'} <= set(CONTRACT['operations'])
    assert 'dashboard_patch' in CONTRACT['tools']


@pytest.mark.parametrize('prefix', ['> ', '- ', '* ', '+ ', '1. ', '2) ', '> - ', '- > ', '>> ', '  > '])
def test_explicit_nested_chart_fences_rejected(prefix):
    with pytest.raises(DashboardError, match='must be top-level'):
        patch_markdown(document(), prefix + '```chart\n' + prefix + '{"componentId":"missing"}\n' + prefix + '```')


def test_nested_chart_examples_inside_ordinary_code_are_inert():
    source = '````markdown\n> ```chart\n> {"componentId":"missing"}\n> ```\n````'
    assert report_chart_references(source) == []
    assert validate(patch_markdown(document(), source))


@pytest.mark.parametrize('source', [
    '> ````markdown\n> ```chart\n> {"componentId":"missing"}\n> ```\n> ````',
    '- ````markdown\n  ```chart\n  {"componentId":"missing"}\n  ```\n  ````',
    '> - ````markdown\n>   ```chart\n>   {"componentId":"missing"}\n>   ```\n>   ````',
    '- > ````markdown\n  > ```chart\n  > {"componentId":"missing"}\n  > ```\n  > ````',
    '    > ```chart\n    > {"componentId":"missing"}\n    > ```',
    '\t> ```chart\n\t> {"componentId":"missing"}\n\t> ```',
])
def test_nested_ordinary_code_and_indented_code_are_inert(source):
    assert report_chart_references(source) == []
    assert validate(patch_markdown(document(), source))


@pytest.mark.parametrize('source', ['> ````markdown\n> Unclosed ordinary code', '- ````markdown\n  Unclosed ordinary code'])
def test_leaving_ordinary_code_container_does_not_hide_later_chart(source):
    with pytest.raises(DashboardError, match='missing component'):
        patch_markdown(document(), source + '\n\n' + fence('missing'))
