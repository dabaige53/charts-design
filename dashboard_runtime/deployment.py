"""Independent static site using the same React components and shared query worker."""
import copy
import gzip
import hashlib
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import uuid
import zipfile

from .assets import DIST, FAVICON_LINK, require_preview, ui_build_id
from .build import BACKEND_BUILD_ID
from .file_lock import exclusive_file_lock
from .model import MAX_BYTES, json_bytes, require

UI_RESOURCES = ('app.js', 'app.css', 'static-worker.js')
INLINE_FILTER_LIMIT = 100
INLINE_FILTER_BYTES = 16 * 1024


def _sha256(path):
    checksum = hashlib.sha256()
    with path.open('rb') as source:
        while block := source.read(1024 * 1024):
            checksum.update(block)
    return checksum.hexdigest()


def _prepare_archive(site, archive, cache_root):
    """Reuse compressed public UI assets; documents and data never enter this cache."""
    key = hashlib.sha256(json_bytes({name: _sha256(site / name) for name in UI_RESOURCES})).hexdigest()
    cache_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = cache_root / key
    with exclusive_file_lock(cache_root / (key + '.lock')):
        try:
            expected = (directory / 'sha256').read_text(encoding='ascii').strip()
        except (OSError, UnicodeError):
            expected = None
        if expected and (directory / 'ui.zip').is_file():
            shutil.copyfile(directory / 'ui.zip', archive)
            if _sha256(archive) == expected:
                return
        # Publish only a complete template. A damaged cache is disposable and
        # repaired while the same lock protects other exporters copying it.
        with TemporaryDirectory(prefix='ui-', dir=cache_root) as temporary:
            staged = Path(temporary) / 'template'
            staged.mkdir()
            with zipfile.ZipFile(staged / 'ui.zip', 'w', zipfile.ZIP_DEFLATED) as output:
                for name in UI_RESOURCES:
                    output.write(site / name, name)
            (staged / 'sha256').write_text(_sha256(staged / 'ui.zip'), encoding='ascii')
            if directory.exists():
                shutil.rmtree(directory)
            staged.rename(directory)
        shutil.copyfile(directory / 'ui.zip', archive)


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


def _static_filter_options(data, manifest, refs):
    """Inline complete small option sets so readers can open filters before loading rows."""
    options = {}
    components = manifest['components']
    for entry in manifest['filters']:
        if entry['op'] != 'in':
            continue
        datasets = dict.fromkeys(components[key]['datasetId'] for key in entry['componentIds'])
        if not all(dataset in refs for dataset in datasets):
            continue
        sources = [refs[dataset] for dataset in datasets]
        field = entry['field']
        if len({source['fields'][field]['type'] for source in sources}) != 1:
            continue
        page = data.option_page(sources, field, limit=INLINE_FILTER_LIMIT)
        if not page['hasMore'] and len(json_bytes(page['values'])) <= INLINE_FILTER_BYTES:
            options[entry['id']] = page['values']
    return options


def export_site(store, board, output_root=None, document=None, data_format='auto', *, single_parquet=False):
    from .model import live_datasets
    require_preview()
    from .columnar import export_format, write_parquet
    data_format, binary = export_format(data_format)
    doc = store.compact(document if document is not None else
                        store.readable(board) if getattr(store, 'project_root', None) else store.get(board, hydrate=False))
    require(not live_datasets(doc), '实时 SQL 看板请通过运行服务查看', 'LIVE_DATA_REQUIRES_RUNTIME')
    doc = copy.deepcopy(doc)
    from .statistical import statistical_artifacts
    doc['statisticalArtifacts'] = {key: {field: value for field, value in artifact.items() if field != 'provenance'}
                                  for key, artifact in statistical_artifacts(store.statistical_document(doc)).items()}
    export_id = uuid.uuid4().hex
    export_root = output_root if output_root is not None else store.root / 'exports'
    export_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = export_root / export_id
    # An export becomes addressable only after every resource and the ZIP exist.
    # Exceptions remove the entire staging directory, including partial copies.
    with TemporaryDirectory(prefix='export-', dir=export_root) as temporary:
        staged = Path(temporary)
        site = staged / 'site'
        (site / 'data').mkdir(mode=0o700, parents=True)
        used = {c.get('datasetId') or c.get('binding', {}).get('datasetId')
                for c in doc['manifest']['components'].values()}
        used.discard(None)
        refs = doc['snapshot'].get('datasetRefs', {})
        doc['staticFiles'] = {}
        counts, encodings = {}, {}

        def write_dataset(key, ref, rows=None):
            if data_format == 'parquet':
                if ref is None:
                    ref = store.data.import_rows(rows, doc['manifest']['datasets'][key]['fields'])
                cache_root = getattr(store, 'runtime_root', store.root) / 'parquet-cache'
                files, count, encoding = write_parquet(site, store.data, ref, cache_root, binary, single_file=single_parquet)
                encodings[key] = encoding
                return files, count
            return _write_shards(site, key, store.data.iter_rows(ref) if ref else rows)

        for key in sorted(used):
            doc['staticFiles'][key], counts[key] = write_dataset(
                key, refs.get(key), iter(doc['snapshot'].get('datasets', {}).get(key, [])))
        for key, ref in doc['snapshot'].get('componentDataRefs', {}).items():
            component = doc['manifest']['components'].get(key)
            if component is None:
                continue
            dataset = 'component-' + key
            component['datasetId'] = dataset
            doc['manifest']['datasets'][dataset] = {'fields': ref['fields']}
            doc['staticFiles'][dataset], counts[dataset] = write_dataset(dataset, ref)
            component['config'].pop('rowsRef', None)
        for key in ('sources', 'queries', 'annotations'):
            doc['manifest'].pop(key, None)
        # A preview response can be re-imported by an authoring client. Runtime
        # capabilities must not become portable content or leak editor tokens.
        for key in ('browserLinks', 'annotationAccess', 'publicationApiBase', 'publication', 'annotationsOpen'):
            doc.pop(key, None)
        doc['staticFilterOptions'] = _static_filter_options(store.data, doc['manifest'], refs)
        doc['snapshot'] = {'datasets': {}}
        doc.pop('computed', None)
        doc.pop('progressive', None)
        doc.pop('loading', None)
        for name in UI_RESOURCES:
            require((DIST / name).is_file(), 'Static UI resource missing: ' + name, 'UI_UNAVAILABLE')
            shutil.copyfile(DIST / name, site / name)
        (site / 'document.json').write_bytes(json_bytes(doc))
        (site / 'index.html').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Charts Design</title>' + FAVICON_LINK + '<link rel="stylesheet" href="app.css"></head><body><div id="root"></div><script>window.__chartsBoot={mode:"static"};</script><script src="app.js"></script></body></html>', encoding='utf-8')
        manifest = {'dashboardId': board, 'revision': doc['revision'], 'uiBuildId': ui_build_id(),
                    'backendBuildId': BACKEND_BUILD_ID, 'dataFormat': data_format,
                    'datasets': counts, 'encodings': encodings}
        (site / 'export-manifest.json').write_bytes(json_bytes(manifest))
        (site / 'README.txt').write_text('将此目录放入普通静态 HTTP 服务。网页按组件加载 data/ 分片，在浏览器本地筛选，不连接 MCP。数据包含使用中的数据集全部记录。\n', encoding='utf-8')
        archive = staged / (board + '.zip')
        _prepare_archive(site, archive, getattr(store, 'runtime_root', store.root) / 'ui-archive-cache')
        with zipfile.ZipFile(archive, 'a', zipfile.ZIP_DEFLATED) as output:
            for path in sorted(site.rglob('*')):
                if path.is_file() and path.relative_to(site).as_posix() not in UI_RESOURCES:
                    output.write(path, path.relative_to(site))
        staged.rename(directory)
    site = directory / 'site'
    archive = directory / (board + '.zip')
    return {'export': {'id': export_id, 'filename': archive.name, 'path': str(archive.resolve()),
                       'directory': str(site.resolve()), 'format': 'zip', 'mimeType': 'application/zip',
                       'bytes': archive.stat().st_size, 'scope': 'static-site-with-used-datasets', 'manifest': manifest}}
