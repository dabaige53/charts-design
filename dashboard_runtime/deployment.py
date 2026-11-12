"""Independent static site using the same React components and shared query worker."""
import copy
import gzip
import shutil
import uuid
import zipfile

from .assets import DIST, FAVICON_LINK, require_preview, ui_build_id
from .build import BACKEND_BUILD_ID
from .model import MAX_BYTES, json_bytes, require


def _write_shards(site, key, rows):
    files, batch, count, size = [], [], 0, 2

    def flush():
        name = 'data/' + key + '-' + str(len(files)) + '.json.gz'
        (site / name).write_bytes(gzip.compress(b'[' + b','.join(batch) + b']', mtime=0))
        files.append(name)

    for row in rows:
        encoded = json_bytes(row)
        require(len(encoded) + 2 <= MAX_BYTES, 'A single export row exceeds the 16 MiB limit', 'PAYLOAD_TOO_LARGE')
        if batch and (len(batch) == 5000 or size + 1 + len(encoded) > MAX_BYTES):
            flush()
            batch, size = [], 2
        size += len(encoded) + bool(batch)
        batch.append(encoded)
        count += 1
    if batch:
        flush()
    return files, count


def export_site(store, board, output_root=None, document=None):
    require_preview()
    doc = store.compact(document if document is not None else
                        store.readable(board) if getattr(store, 'project_root', None) else store.get(board, hydrate=False))
    doc = copy.deepcopy(doc)
    from .statistical import statistical_artifacts
    doc['statisticalArtifacts'] = {key: {field: value for field, value in artifact.items() if field != 'provenance'}
                                  for key, artifact in statistical_artifacts(store.statistical_document(doc)).items()}
    export_id = uuid.uuid4().hex
    directory = (output_root if output_root is not None else store.root / 'exports') / export_id
    site = directory / 'site'
    (site / 'data').mkdir(mode=0o700, parents=True)
    used = {c.get('datasetId') for c in doc['manifest']['components'].values() if c.get('datasetId')}
    refs = doc['snapshot'].get('datasetRefs', {})
    doc['staticFiles'] = {}
    counts = {}
    for key in sorted(used):
        rows = store.data.iter_rows(refs[key]) if key in refs else iter(doc['snapshot'].get('datasets', {}).get(key, []))
        doc['staticFiles'][key], counts[key] = _write_shards(site, key, rows)
    for key, ref in doc['snapshot'].get('componentDataRefs', {}).items():
        component = doc['manifest']['components'].get(key)
        if component is None:
            continue
        dataset = 'component-' + key
        component['datasetId'] = dataset
        doc['manifest']['datasets'][dataset] = {'fields': ref['fields']}
        doc['staticFiles'][dataset], counts[dataset] = _write_shards(site, dataset, store.data.iter_rows(ref))
        component['config'].pop('rowsRef', None)
    for key in ('sources', 'queries', 'annotations'):
        doc['manifest'].pop(key, None)
    doc['snapshot'] = {'datasets': {}}
    doc.pop('computed', None)
    doc.pop('progressive', None)
    doc.pop('loading', None)
    for name in ('app.js', 'app.css', 'static-worker.js'):
        require((DIST / name).is_file(), 'Static UI resource missing: ' + name, 'UI_UNAVAILABLE')
        shutil.copyfile(DIST / name, site / name)
    (site / 'document.json').write_bytes(json_bytes(doc))
    (site / 'index.html').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Charts Design</title>' + FAVICON_LINK + '<link rel="stylesheet" href="app.css"></head><body><div id="root"></div><script>window.__chartsBoot={mode:"static"};</script><script src="app.js"></script></body></html>', encoding='utf-8')
    manifest = {'dashboardId': board, 'revision': doc['revision'], 'uiBuildId': ui_build_id(), 'backendBuildId': BACKEND_BUILD_ID, 'datasets': counts}
    (site / 'export-manifest.json').write_bytes(json_bytes(manifest))
    (site / 'README.txt').write_text('将此目录放入普通静态 HTTP 服务。网页按组件加载 data/ 分片，在浏览器本地筛选，不连接 MCP。数据包含使用中的数据集全部记录。\n', encoding='utf-8')
    archive = directory / (board + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
        for path in sorted(site.rglob('*')):
            if path.is_file():
                output.write(path, path.relative_to(site))
    return {'export': {'id': export_id, 'filename': archive.name, 'path': str(archive.resolve()),
                       'directory': str(site.resolve()), 'format': 'zip', 'mimeType': 'application/zip',
                       'bytes': archive.stat().st_size, 'scope': 'static-site-with-used-datasets', 'manifest': manifest}}
