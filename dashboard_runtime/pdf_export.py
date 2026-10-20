"""Paginated local PDF: complete component images and streamed detail tables."""
from __future__ import annotations

import base64
from html import escape
from itertools import islice
from pathlib import Path
import shutil
import subprocess
import tempfile

from .model import require

STYLE = '''body{font-family:-apple-system,"PingFang SC",sans-serif;color:#17212b;font-size:11px;margin:0}
h1{font-size:24px;color:#123b5d;margin:0 0 10px}h2{font-size:16px;color:#123b5d;margin:0 0 12px}
p{line-height:1.7;color:#52606d}.figures{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:14px}
figure{margin:0;break-inside:avoid;align-self:start}img{display:block;width:100%;height:auto}
table{border-collapse:collapse;width:100%;table-layout:fixed;font-size:10px}thead{display:table-header-group}
th,td{border:1px solid #e2e7eb;padding:6px 7px;text-align:left;overflow-wrap:anywhere}
th{background:#edf3f7;color:#123b5d}tr{break-inside:avoid}th.numeric,td.numeric{text-align:right}
*{-webkit-print-color-adjust:exact;print-color-adjust:exact}'''


def shell(body):
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>' + STYLE + '</style><body>' + body + '</body></html>'


def render_pdf(path: Path, document: dict, html: str, data):
    from playwright.sync_api import sync_playwright
    merger = shutil.which('pdfunite')
    require(merger is not None, '完整 PDF 导出需要本机 pdfunite，当前没有可用的 PDF 合并工具')
    assert merger is not None
    manifest = document['manifest']
    computed = document.get('computed', {})
    options = {'format': 'A3', 'landscape': True, 'print_background': True,
               'margin': {'top': '12mm', 'bottom': '12mm', 'left': '10mm', 'right': '10mm'}}
    parts = []
    table_counts = {}
    with tempfile.TemporaryDirectory(prefix='pdf-', dir=path.parent) as working, sync_playwright() as playwright:
        folder = Path(working)
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=2)
            page.set_content(html.replace('window.__DASHBOARD_BOOT__=', 'window.__CHARTS_PDF_EXPORT__=true;window.__DASHBOARD_BOOT__=', 1), wait_until='load')
            page.wait_for_selector('.grid-stack-item, .report-paper, .markdown-preview', timeout=30000)
            page.evaluate('document.fonts.ready')
            page.wait_for_timeout(1100)
            # Screenshots preserve each renderer's visuals, including shadow-root styles.
            # The print document owns pagination; no fixed grid or overflow containers remain.
            page.evaluate('''() => {
              for(const host of document.querySelectorAll('.original-host')){
                if(!host.shadowRoot)continue;
                const s=document.createElement('style');s.textContent=`
                  button,input,select,.component-actions,.chart-action-btn,.catalog-search{visibility:hidden!important}
                  .section-card{box-shadow:none!important}`;host.shadowRoot.append(s);
              }
            }''')
            figures = []
            tables = []
            for position in sorted(manifest['layout']['desktop'], key=lambda p: (p['y'], p['x'])):
                key = position['id']
                component = manifest['components'][key]
                if component.get('family', component['kind']) == 'table':
                    tables.append((key, component))
                    continue
                if manifest.get('viewMode') == 'report':
                    continue
                locator = page.locator('[data-component-id="' + key + '"] .grid-stack-item-content')
                if not locator.count():
                    locator = page.locator('[data-component-id="' + key + '"]').first
                image = base64.b64encode(locator.screenshot()).decode('ascii')
                figures.append('<figure style="grid-column:span ' + str(position['w']) + '"><img alt="' + escape(component['title'], quote=True) + '" src="data:image/png;base64,' + image + '"></figure>')
            title = escape(manifest['title'])
            filters = '；'.join(escape(str(f.get('label', f['field']))) + '：' + escape('、'.join(map(str, f['values']))) for f in manifest['filters'] if f['values'])
            cover = shell('<h1>' + title + '</h1><p>' + (filters or '全部筛选范围') + '</p><div class="figures">' + ''.join(figures) + '</div>')
            if manifest.get('viewMode') == 'report':
                images = []
                for host in page.locator('.markdown-preview .original-host').all():
                    images.append(None if host.evaluate('(h)=>!!h.shadowRoot?.querySelector("#app-table-section")') else base64.b64encode(host.screenshot()).decode('ascii'))
                cover = page.evaluate('''images=>{
                  const article=document.querySelector('.markdown-preview').cloneNode(true);
                  article.querySelectorAll('.original-host').forEach((host,i)=>{
                    if(images[i]){const img=document.createElement('img');img.src='data:image/png;base64,'+images[i];img.style='width:100%;height:auto';host.replaceWith(img);}
                    else{const p=document.createElement('p');p.textContent='完整表格见后附明细';host.replaceWith(p);}
                  });
                  return '<!doctype html><html lang="zh-CN"><head>'+document.head.innerHTML+'</head><body>'+article.outerHTML+'</body></html>';
                }''', images)
            printer = browser.new_page(viewport={'width': 1440, 'height': 1000})

            def print_part(body):
                target = folder / (str(len(parts)) + '.pdf')
                printer.set_content(body, wait_until='load')
                printer.evaluate('document.fonts.ready')
                printer.pdf(path=str(target), **options)
                parts.append(target)

            print_part(cover)
            for key, component in tables:
                raw = computed.get('components', {}).get(key, component.get('config', {}))
                columns = raw.get('columns') or component.get('presentation', {}).get('columns', [])
                state = computed.get('tables', {}).get(key, {})
                ds = component.get('datasetId')
                snapshot = document['snapshot']
                ref = snapshot.get('datasetRefs', {}).get(ds) if ds else snapshot.get('componentDataRefs', {}).get(key)
                if ref:
                    require(data is not None, '完整表格导出需要本机数据版本')
                    active = [f for f in manifest['filters'] if key in f['componentIds'] and f['values']]
                    sort = [{'field': state['sortCol'], 'direction': state.get('sortDir', 'asc')}] if state.get('sortCol') else []
                    rows = iter(data.iter_rows(ref, active, columns=[c['key'] for c in columns], sort=sort, search=state.get('keyword', '')))
                else:
                    rows = iter(raw.get('rows', []))
                count = 0
                header = ''.join('<th>' + escape(str(c.get('title', c['key']))) + '</th>' for c in columns)
                while True:
                    batch = list(islice(rows, 1000))
                    if not batch and count:
                        break
                    body = ''.join('<tr>' + ''.join('<td>' + escape(str(row.get(c['key'], '') if row.get(c['key']) is not None else '—')) + '</td>' for c in columns) + '</tr>' for row in batch)
                    first = count + 1 if batch else 0
                    count += len(batch)
                    heading = '<h2>' + escape(component['title']) + '</h2><p>明细 ' + str(first) + '–' + str(count) + ' 条 · 当前筛选全部明细</p>'
                    print_part(shell(heading + '<table><thead><tr>' + header + '</tr></thead><tbody>' + body + '</tbody></table>'))
                    if not batch:
                        break
                if ref:
                    require(count == state['totalRows'], 'PDF 明细行数与筛选结果不一致，已取消导出')
                table_counts[key] = count
            # Keep merge invocations bounded even for very large exports.
            round_number = 0
            while len(parts) > 1:
                merged = []
                for offset in range(0, len(parts), 64):
                    target = folder / ('merged-' + str(round_number) + '-' + str(offset) + '.pdf')
                    subprocess.run([merger, *map(str, parts[offset:offset+64]), str(target)], check=True, capture_output=True)
                    merged.append(target)
                parts = merged
                round_number += 1
            shutil.copyfile(parts[0], path)
            return {'tableRows': table_counts, 'tableScope': 'all-filtered-rows'}
        finally:
            browser.close()
