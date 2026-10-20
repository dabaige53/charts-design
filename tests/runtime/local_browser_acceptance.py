"""Optional local acceptance: stdio MCP + official AppBridge, with no HTTP listener."""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextResourceContents
from playwright.async_api import async_playwright, expect
from pydantic import AnyUrl

from dashboard_runtime.assets import render_html
from dashboard_runtime.service import Service


REPO = Path(__file__).resolve().parents[2]


async def accept(workspace, output, originals=None):
    output.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='.browser-', dir=output))
    store = root / 'store'
    store.mkdir()
    # Clone immutable synthetic data; no source or original dashboard is modified.
    with sqlite3.connect(workspace / 'store' / 'data.sqlite3') as source, sqlite3.connect(store / 'data.sqlite3') as target:
        source.backup(target)
    with sqlite3.connect(workspace / 'store' / 'dashboards.sqlite3') as db:
        row = db.execute("SELECT document FROM boards WHERE id='acceptance'").fetchone()
        assert row is not None
        synthetic = json.loads(row[0])
    service = Service(store, workspace / 'sources.json')
    service.store.create('acceptance', synthetic['manifest']['title'], synthetic)
    documents = {}
    if originals:
        with sqlite3.connect(originals.as_uri() + '?mode=ro', uri=True) as db:
            for board, raw in db.execute("SELECT id,document FROM boards WHERE id IN ('domestic-channel-overview-20261019','domestic-transfer-analysis-20261019')"):
                documents[board] = {'raw': raw, 'document': json.loads(raw), 'sha256': hashlib.sha256(raw.encode()).hexdigest()}
                service.store.create(board, documents[board]['document']['manifest']['title'], documents[board]['document'])
        assert len(documents) == 2
    bundle = root / 'host.js'
    subprocess.run([str(REPO / 'runtime-ui/node_modules/esbuild/bin/esbuild'),
                    str(REPO / 'tests/runtime/mcp-app-host.mjs'), '--bundle', '--format=esm', f'--outfile={bundle}'],
                   check=True, capture_output=True)
    params = StdioServerParameters(command='node', args=[str(REPO / 'bin/dashboard-runtime.js'), '--root', str(store),
        '--sources', str(workspace / 'sources.json'), 'mcp'], env=dict(os.environ))
    report = {'transport': 'stdio MCP + official AppBridge fixture; not the Codex desktop host',
              'httpListenersStarted': 0, 'workspace': str(root), 'originals': {}, 'calls': []}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def call(name, arguments):
                started = time.perf_counter()
                result = await session.call_tool(name, arguments)
                assert not result.isError, result
                assert result.structuredContent is not None
                record = {'tool': name, 'durationMs': (time.perf_counter()-started)*1000,
                          'bytes': len(result.model_dump_json(by_alias=True, exclude_none=True).encode())}
                if 'document' in result.structuredContent:
                    doc = result.structuredContent['document']
                    assert doc['snapshot']['datasets'] == {}
                    record['sourceRows'] = doc.get('computed', {}).get('sourceRows', {})
                report['calls'].append(record)
                return result

            resources = await session.list_resources()
            uri = next(r.uri for r in resources.resources if str(r.uri).startswith('ui://'))
            resource = await session.read_resource(AnyUrl(str(uri)))
            content = resource.contents[0]
            assert isinstance(content, TextResourceContents)
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                try:
                    async def open_board(board):
                        result = await call('dashboard_preview', {'dashboardId': board})
                        assert result.structuredContent is not None
                        page = await browser.new_page(viewport={'width': 1600, 'height': 1200})
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))

                        async def handle(_source, request):
                            response = await call(request['name'], request.get('arguments', {}))
                            return response.model_dump(by_alias=True, exclude_none=True)

                        await page.expose_binding('mcpCallTool', handle)
                        await page.add_init_script('window.initialResult=' + result.model_dump_json(by_alias=True, exclude_none=True))
                        async def route(request):
                            url = request.request.url
                            await request.fulfill(content_type='text/html' if not url.endswith('/host.js') else 'text/javascript',
                                body=content.text if url.endswith('/app') else bundle.read_text() if url.endswith('/host.js') else '<!doctype html><script type="module" src="/host.js"></script>')
                        await page.route('http://127.0.0.1:54321/**', route)
                        await page.goto('http://127.0.0.1:54321/')
                        app = page.frame_locator('#app')
                        await app.locator('canvas').first.wait_for()
                        await expect(app.get_by_label('Dashboard title')).to_have_value(result.structuredContent['document']['manifest']['title'])
                        return page, app, errors, result.structuredContent['document']

                    page, app, errors, initial = await open_board('acceptance')
                    table = app.locator('[data-component-id="details"]')
                    total = initial['computed']['tables']['details']['totalRows']
                    assert total >= 1_000_000
                    assert await table.locator('tbody tr').count() == 10
                    await table.get_by_role('button', name='下一页', exact=True).click()
                    await expect(table.locator('#tablePageIndicator')).to_have_text(f'2 / {(total+9)//10}')
                    await table.locator('th').filter(has_text='rowId').click()
                    await expect(table.locator('#tablePageIndicator')).to_have_text(f'1 / {(total+9)//10}')
                    row_id_index = [c['key'] for c in initial['computed']['components']['details']['columns']].index('rowId')
                    await expect(table.locator('tbody tr').first.locator('td').nth(row_id_index)).to_contain_text(str(total-1))
                    await app.get_by_role('button', name='Department：全部', exact=True).click()
                    for check in await app.locator('.filter-choice input').all():
                        await check.uncheck()
                    await app.locator('.filter-choice').filter(has_text='Department-1').locator('input').check()
                    await app.get_by_role('button', name='应用筛选', exact=True).click()
                    await expect(table.locator('#tablePaginationInfo')).to_contain_text(f'共 {total//4} 条')
                    await table.get_by_label('搜索明细').fill('Agent-01')
                    expected_search = sum(i % 97 == 1 for i in range(1, total, 4))
                    await expect(table.locator('#tablePaginationInfo')).to_contain_text(f'共 {expected_search} 条', timeout=15000)
                    assert 'Agent-01' in await table.locator('tbody').inner_text()
                    await table.get_by_label('搜索明细').fill('')
                    await expect(table.locator('#tablePaginationInfo')).to_contain_text(f'共 {total//4} 条', timeout=15000)
                    await table.get_by_role('button', name='导出表格 CSV', exact=True).click()
                    await expect(table.locator('#app-toast-container')).to_contain_text(f'已导出 {total//4} 条', timeout=20000)
                    files = list((store / 'exports').glob('*.csv'))
                    assert len(files) == 1
                    with files[0].open(encoding='utf-8-sig', newline='') as handle:
                        assert sum(1 for _ in csv.DictReader(handle)) == total//4
                    await page.screenshot(path=str(output / 'million-rows.png'), full_page=True)
                    report['millionBrowser'] = {'status': 'passed', 'rows': total, 'renderedTableRows': 10,
                        'filteredRows': total//4, 'filteredExportRows': total//4, 'pageErrors': errors}
                    canonical = await call('dashboard_get', {'dashboardId': 'acceptance'})
                    assert canonical.structuredContent is not None
                    saved = canonical.structuredContent['document']
                    filters = [*saved['manifest']['filters'], {'id': 'row-selector', 'field': 'rowId', 'label': 'Row ID',
                        'op': 'in', 'values': [], 'componentIds': list(saved['manifest']['components'])}]
                    updated = await call('dashboard_patch', {'dashboardId': 'acceptance', 'expectedRevision': saved['revision'],
                        'operations': [{'op': 'set_filters', 'value': filters}]})
                    await page.evaluate('result=>window.deliverToolResult(result)', updated.model_dump(by_alias=True, exclude_none=True))
                    await app.get_by_role('button', name='Row ID：全部', exact=True).click()
                    await app.get_by_label('Row ID搜索选项').fill(str(total-1))
                    await expect(app.locator('.filter-choice')).to_have_count(1, timeout=15000)
                    await app.locator('.filter-choice input').check()
                    await app.get_by_role('button', name='应用筛选', exact=True).click()
                    await expect(table.locator('#tablePaginationInfo')).to_contain_text('共 1 条', timeout=15000)
                    report['millionBrowser']['optionUniverse'] = total
                    report['millionBrowser']['lastOptionSelected'] = total-1
                    assert not errors
                    await page.close()

                    for board, source in documents.items():
                        page, app, errors, prepared = await open_board(board)
                        await page.wait_for_timeout(500)
                        await page.locator('#app').evaluate('(frame)=>frame.style.height=frame.contentDocument.documentElement.scrollHeight+"px"')
                        await page.screenshot(path=str(output / (board + '.png')), full_page=True)
                        # Compare original browser calculations and first table page with the local query path.
                        snapshot = '''body=>Object.fromEntries([...body.querySelectorAll('.grid-stack-item[data-component-id]')].map(host=>{
                          const shadow=host.shadowRoot||host.querySelector('.grid-stack-item-content')?.shadowRoot;
                          const owner=shadow?.__dashboardApp;
                          const kpi=owner?.config.kpis?.[0];
                          const series=Object.values(owner?.state.chartInstances||{})[0]?.getOption()?.series?.map(s=>({name:s.name,type:s.type,data:s.data}));
                          const columns=owner?.state.table?.orderedColumns?.filter(c=>owner.state.table.visibleCols.has(c.key)).map(c=>c.key);
                          const rows=shadow?[...shadow.querySelectorAll('tbody tr')].map(row=>[...row.querySelectorAll('td')].map(cell=>cell.textContent.trim())):[];
                          return [host.dataset.componentId,{kpi:kpi?Object.fromEntries(['value','leftVal','rightVal','yoy','mom'].filter(k=>k in kpi).map(k=>[k,kpi[k]])):null,series:series||null,columns:columns||[],rows}];
                        }))'''
                        local_visual = await app.locator('body').evaluate(snapshot)
                        baseline = await browser.new_page(viewport={'width': 1600, 'height': 1200})
                        original_html = render_html('offline', source['document'])
                        await baseline.route('http://127.0.0.1:54322/**', lambda route: route.fulfill(content_type='text/html', body=original_html))
                        await baseline.goto('http://127.0.0.1:54322/')
                        await baseline.locator('canvas').first.wait_for()
                        baseline_visual = await baseline.locator('body').evaluate(snapshot)
                        assert local_visual == baseline_visual, {'board': board, 'local': local_visual, 'baseline': baseline_visual}
                        await baseline.screenshot(path=str(output / (board + '-baseline.png')), full_page=True)
                        await baseline.close()
                        cards = len(prepared['manifest']['components'])
                        assert await app.locator('.grid-stack-item[data-component-id]').count() == cards
                        assert not await app.locator('.grid-stack-item-content>p.error').count()
                        table_id = next(key for key, c in prepared['manifest']['components'].items() if c.get('kind') == 'table' or c.get('family') == 'table')
                        shown = app.locator(f'[data-component-id="{table_id}"]')
                        if prepared['computed']['tables'][table_id]['totalRows'] > 10:
                            await shown.get_by_role('button', name='下一页', exact=True).click()
                            await expect(shown.locator('#tablePageIndicator')).to_contain_text('2 /')
                        report['originals'][board] = {'status': 'passed', 'revision': source['document']['revision'],
                            'originalDocumentSha256': source['sha256'], 'components': cards, 'pageErrors': errors,
                            'originalBrowserValuesAndFirstPageMatch': True,
                            'localResponseBytes': len(json.dumps(prepared, ensure_ascii=False).encode())}
                        assert not errors
                        await page.close()
                finally:
                    await browser.close()
    if originals:
        with sqlite3.connect(originals.as_uri() + '?mode=ro', uri=True) as db:
            for board, source in documents.items():
                record = db.execute('SELECT document FROM boards WHERE id=?', (board,)).fetchone()
                assert record is not None and record[0] == source['raw']
        report['originalDocumentsUnchanged'] = True
    report['status'] = 'passed'
    (output / 'browser-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'passed', 'report': str(output / 'browser-report.json')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--originals', type=Path)
    args = parser.parse_args()
    asyncio.run(accept(args.workspace.resolve(), args.output.resolve(), args.originals.resolve() if args.originals else None))


if __name__ == '__main__':
    main()
