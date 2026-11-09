"""Markdown reports reuse v2 components, revisions and the export boundary."""
import copy
import json
import re
import subprocess
import sys

import pytest

from dashboard_runtime import assets
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


# @wu-test type=behavior | scope=旧文档 | protects=校验旧文档修改内容
def test_old_documents_remain_valid_and_unchanged():
    doc = document()
    before = copy.deepcopy(doc)
    assert validate(doc) is doc
    assert doc == before
    assert 'viewMode' not in doc['manifest'] and 'report' not in doc['manifest']


# @wu-test type=behavior | scope=报告模式 | protects=初始化报告改变布局组件数据
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


# @wu-test type=behavior | scope=报告正文 | protects=模式切换清空改写正文
def test_canonical_source_survives_mode_switches_and_accepts_empty_report():
    for source in ('', '# Analysis\n\n**Finding.**\n\n' + fence('regions') + '\n\n' + fence('trend')):
        doc = patch_markdown(document(), source)
        assert 'viewMode' not in doc['manifest']
        for mode in ('report', 'dashboard', 'report'):
            doc = apply_operations(doc, [{'op': 'set_view_mode', 'value': mode}])
            assert doc['manifest']['report'] == {'markdown': source}


# @wu-test type=boundary | scope=旧报告兼容 | protects=缺元数据或空旧报告不能用
def test_absent_report_metadata_and_legacy_empty_report_are_valid():
    doc = new_document('empty', 'Empty')
    doc['manifest']['viewMode'] = 'report'
    assert validate(doc)
    assert patch_legacy(doc, legacy_report())['manifest']['report']['blocks'] == []


# @wu-test type=boundary | scope=视图模式 | protects=非法模式通过操作导入
@pytest.mark.parametrize('value', [None, 'slides', '', 0, {}, []])
def test_invalid_view_mode_is_rejected(value):
    with pytest.raises(DashboardError, match='Unknown view mode'):
        apply_operations(document(), [{'op': 'set_view_mode', 'value': value}])
    doc = document()
    doc['manifest']['viewMode'] = value
    with pytest.raises(DashboardError, match='Unknown view mode'):
        validate(doc)


# @wu-test type=boundary | scope=报告正文 | protects=非字符串超长正文被保存
@pytest.mark.parametrize('source', [None, 0, {}, [], 'x' * (MAX_REPORT_MARKDOWN + 1)])
def test_markdown_type_and_limit(source):
    with pytest.raises(DashboardError, match='markdown must contain'):
        patch_markdown(document(), source)
    doc = document()
    doc['manifest']['report'] = {'markdown': source}
    with pytest.raises(DashboardError, match='markdown must contain'):
        validate(doc)


# @wu-test type=boundary | scope=Markdown | protects=最大合法长度被拒或普通代码误识别
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


# @wu-test type=boundary | scope=图表代码块 | protects=畸形JSON无效组件错误围栏被保存
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


# @wu-test type=boundary | scope=报告引用 | protects=文本被当图表或重复合法引用被拒
def test_chart_fences_require_non_text_references_and_allow_repetition():
    doc = apply_operations(document(), [{'op': 'put_component', 'id': 'note', 'value': {'kind': 'text', 'title': 'Note', 'text': 'Plain'}}])
    with pytest.raises(DashboardError, match='non-text'):
        patch_markdown(doc, fence('note'))
    source = '\n\n'.join(fence(key) for key in ('trend', 'total', 'details', 'trend'))
    assert report_chart_references(patch_markdown(doc, source)['manifest']['report']['markdown']) == ['trend', 'total', 'details', 'trend']


# @wu-test type=boundary | scope=图注元数据 | protects=合法图注来源原文丢失
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


# @wu-test type=boundary | scope=图注元数据 | protects=非法类型超长元数据进入报告
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


# @wu-test type=boundary | scope=图表代码块 | protects=缺组件重复键未知键因元数据被接受
@pytest.mark.parametrize('payload', [
    '{"caption":"Missing component"}',
    '{"componentId":"trend","caption":"one","caption":"two"}',
    '{"componentId":"trend","source":"one","source":"two"}',
    '{"componentId":"trend","caption":"valid","unknown":"bad"}',
])
def test_metadata_does_not_relax_required_or_unique_chart_keys(payload):
    with pytest.raises(DashboardError):
        patch_markdown(document(), '```chart\n' + payload + '\n```')


# @wu-test type=behavior | scope=Markdown围栏 | protects=合法波浪线缩进换行不识别
@pytest.mark.parametrize('source', [
    '~~~chart\n{"componentId":"trend"}\n~~~~',
    '   ```chart \n{"componentId":"trend"}\n   ```\t',
    '````chart\n{"componentId":"trend"}\n`````',
    '```chart\r\n{"componentId":"trend"}\r\n```',
])
def test_supported_fence_variants(source):
    assert report_chart_references(source, document()['manifest']['components']) == ['trend']


# @wu-test type=boundary | scope=Markdown代码块 | protects=普通代码误作图表引用
def test_non_chart_languages_and_indented_examples_are_not_references():
    assert report_chart_references('```javascript\nanything\n```') == []
    assert report_chart_references('```Chart\nanything\n```') == []
    assert report_chart_references('    ```chart\n    anything\n    ```') == []


# @wu-test type=behavior | scope=报告编辑 | protects=修改组件擅自改写正文
def test_new_component_does_not_insert_source_and_updates_preserve_source():
    source = '# Draft\n\n' + fence('trend')
    doc = patch_markdown(document(), source)
    doc = apply_operations(doc, [
        {'op': 'put_component', 'id': 'trend', 'value': {**doc['manifest']['components']['trend'], 'title': 'Revised'}},
        {'op': 'put_component', 'id': 'note', 'value': {'kind': 'text', 'title': '', 'text': 'Unlisted'}},
    ])
    assert doc['manifest']['report'] == {'markdown': source}
    assert all(any(p['id'] == 'note' for p in layout) for layout in doc['manifest']['layout'].values())


# @wu-test type=boundary | scope=报告组件删除 | protects=删除被引用组件造成悬空或部分修改
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


# @wu-test type=behavior | scope=报告批量编辑 | protects=同批先引用后创建错误拒绝
def test_references_can_precede_creation_in_atomic_batch():
    doc = document()
    updated = apply_operations(doc, [
        {'op': 'set_report_markdown', 'value': fence('new-chart')},
        {'op': 'put_component', 'id': 'new-chart', 'value': doc['manifest']['components']['trend']},
        {'op': 'set_view_mode', 'value': 'report'},
    ])
    assert updated['manifest']['report']['markdown'] == fence('new-chart')


# @wu-test type=boundary | scope=报告引用 | protects=被引用图表替换文本留无效引用
def test_changing_referenced_chart_to_text_is_rejected():
    doc = patch_markdown(document(), fence('trend'))
    with pytest.raises(DashboardError, match='non-text'):
        apply_operations(doc, [{'op': 'put_component', 'id': 'trend', 'value': {'kind': 'text', 'title': '', 'text': 'Replacement'}}])


# @wu-test type=integration | scope=旧报告迁移 | protects=迁移执行代码或改坏内容
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


# @wu-test type=behavior | scope=旧报告批处理 | protects=同批稍后创建内容未进入迁移
def test_legacy_migration_waits_for_later_references_in_batch():
    doc = apply_operations(document(), [
        {'op': 'set_report', 'value': legacy_report('new-note', 'trend')},
        {'op': 'set_view_mode', 'value': 'report'},
        {'op': 'put_component', 'id': 'new-note', 'value': {'kind': 'text', 'title': 'Finding', 'text': 'Authored finding'}},
    ])
    assert 'Authored finding' in doc['manifest']['report']['markdown']
    assert report_chart_references(doc['manifest']['report']['markdown']) == ['trend']


# @wu-test type=behavior | scope=报告正文优先级 | protects=旧引用阻止删除已不引用组件
def test_canonical_source_overrides_stale_legacy_references():
    doc = patch_legacy(document(), legacy_report('trend', 'regions'))
    doc = patch_markdown(doc, '# Independent source')
    doc = apply_operations(doc, [{'op': 'remove_component', 'id': 'trend'}])
    assert doc['manifest']['report']['blocks'] == legacy_report('trend', 'regions')['blocks']
    assert report_markdown(doc['manifest']) == '# Independent source'
    assert validate(doc)


# @wu-test type=boundary | scope=旧报告输入 | protects=非法结构重复引用超限报告被接受
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


# @wu-test type=behavior | scope=旧报告编辑 | protects=旧接口新增删除未更新blocks
def test_legacy_set_report_still_replaces_and_manages_blocks():
    doc = patch_markdown(document(), '# Modern')
    doc = patch_legacy(doc, legacy_report('trend'))
    assert 'markdown' not in doc['manifest']['report']
    doc = apply_operations(doc, [{'op': 'put_component', 'id': 'note', 'value': {'kind': 'text', 'title': '', 'text': 'Legacy'}}])
    assert doc['manifest']['report'] == legacy_report('trend', 'note')
    doc = apply_operations(doc, [{'op': 'remove_component', 'id': 'trend'}])
    assert doc['manifest']['report'] == legacy_report('note')


# @wu-test type=boundary | scope=旧报告blocks | protects=合法上限失败或碰撞ID重复
def test_legacy_report_limits_and_block_id_collisions_remain_supported():
    doc = patch_legacy(new_document('bounded', 'Bounded'), legacy_report(subtitle='x' * 1000))
    doc = apply_operations(doc, [{'op': 'put_component', 'id': f'note-{n}', 'value': {'kind': 'text', 'title': '', 'text': ''}} for n in range(100)])
    assert len(doc['manifest']['report']['blocks']) == 100
    key = 'n' * 80
    doc = patch_legacy(document(), {'subtitle': '', 'blocks': [{'id': key, 'componentId': 'trend'}, {'id': key[:78] + '-2', 'componentId': 'regions'}]})
    doc = apply_operations(doc, [{'op': 'put_component', 'id': key, 'value': {'kind': 'text', 'title': '', 'text': ''}}])
    assert doc['manifest']['report']['blocks'][-1] == {'id': key[:78] + '-3', 'componentId': key}


# @wu-test type=integration | scope=报告持久化 | protects=非法批次部分保存或恢复错误版本
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




# @wu-test type=integration | scope=报告CLI | protects=初始化导出导入丢报告
def test_cli_report_init_demo_json_export_and_import(tmp_path):
    def run(*args):
        return subprocess.run([sys.executable, '-m', 'dashboard_runtime', '--project-root', str(tmp_path / 'cli'), '--runtime-root', str(tmp_path / 'cache'), *args], text=True, capture_output=True)

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


# @wu-test type=boundary | scope=离线报告导出 | protects=正文脚本注入或单组件残留报告
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




# @wu-test type=boundary | scope=嵌套图表围栏 | protects=引用列表内围栏被当顶层图表
@pytest.mark.parametrize('prefix', ['> ', '- ', '* ', '+ ', '1. ', '2) ', '> - ', '- > ', '>> ', '  > '])
def test_explicit_nested_chart_fences_rejected(prefix):
    with pytest.raises(DashboardError, match='must be top-level'):
        patch_markdown(document(), prefix + '```chart\n' + prefix + '{"componentId":"missing"}\n' + prefix + '```')


# @wu-test type=boundary | scope=普通代码图表示例 | protects=示例代码执行或被当引用
def test_nested_chart_examples_inside_ordinary_code_are_inert():
    source = '````markdown\n> ```chart\n> {"componentId":"missing"}\n> ```\n````'
    assert report_chart_references(source) == []
    assert validate(patch_markdown(document(), source))


# @wu-test type=boundary | scope=嵌套普通代码 | protects=引用列表缩进代码被误识别
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


# @wu-test type=boundary | scope=Markdown容器结束 | protects=未闭合嵌套代码掩盖后续非法图表
@pytest.mark.parametrize('source', ['> ````markdown\n> Unclosed ordinary code', '- ````markdown\n  Unclosed ordinary code'])
def test_leaving_ordinary_code_container_does_not_hide_later_chart(source):
    with pytest.raises(DashboardError, match='missing component'):
        patch_markdown(document(), source + '\n\n' + fence('missing'))
