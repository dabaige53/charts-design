"""Code-protected static publications; expiration cleanup runs only in cloud SCF."""
from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import tempfile
import time
import uuid
import copy
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from .model import DashboardError, identifier, json_bytes, require, utcnow, validate_annotations

SHARE_ID = re.compile(r'^[0-9a-f]{32}$')
ACCESS_KEY = re.compile(r'^[0-9]{8}$')
EXPIRATIONS = {'never': None, '7d': 7 * 86400, '30d': 30 * 86400}


def checked_annotation_mode(value):
    require(value in ('view', 'annotate'), 'annotationMode must be view or annotate', 'INVALID_ARGUMENT')
    return value


def checked_id(value):
    require(isinstance(value, str) and bool(SHARE_ID.fullmatch(value)),
            'Invalid cloud share ID', 'INVALID_ARGUMENT')
    return value


def key_digest(key, salt):
    return hashlib.pbkdf2_hmac('sha256', key.encode(), bytes.fromhex(salt), 200000).hex()


def retire_id(storage, share_id):
    # The opaque ID alone is retained; no owner, credential, content or feedback.
    storage.put('retired/' + checked_id(share_id), b'')


class CloudShares:
    def __init__(self, storage, public_url):
        self.storage = storage
        self.executor = getattr(storage, 'executor', 'tencent-scf')
        parsed = urlparse(public_url)
        require(parsed.scheme == 'https' and bool(parsed.netloc) and not parsed.query and not parsed.fragment,
                'Configure CHARTS_PUBLIC_URL as the HTTPS cloud gateway address',
                'CLOUD_SHARE_NOT_CONFIGURED')
        self.public_url = public_url.rstrip('/')

    @classmethod
    def from_environment(cls, public_url=None):
        public_url = public_url or os.environ.get('CHARTS_PUBLIC_URL', '')
        if os.environ.get('CHARTS_STORAGE_BACKEND') in ('cloudflare', 'neon'):
            from .cloudflare_shares import storage
            return cls(storage(), public_url)
        from .cloud_storage import CosShareStorage
        return cls(CosShareStorage.from_environment(), public_url)

    def _put_json(self, key, value):
        self.storage.put(key, json.dumps(value, ensure_ascii=False, allow_nan=False).encode(), 'application/json')

    def _not_retired(self, share_id):
        require(self.storage.get('retired/' + checked_id(share_id)) is None,
                'Share has expired or been revoked', 'SHARE_EXPIRED')

    def _annotations(self):
        from .share_annotations import annotation_store
        return annotation_store(self.storage)

    def _configure_annotations(self, control, *, force=False):
        if control.get('annotationMode') != 'annotate' and not force:
            return
        database = self._annotations()
        # Verify the deployed RPC before leaving any task which needs it.
        database.call('ready', shareId=control['shareId'])
        intent_key = 'publication-intents/' + control['shareId'] + '.json'
        if self.storage.get(intent_key) is None:
            self._put_json(intent_key, {'shareId': control['shareId'], 'cleanupAfter': control['stagingUntil']})
        result = database.call('configure', shareId=control['shareId'], owner=control['owner'],
                               pages=control['pages'], expiresAt=control['expiresAt'],
                               stagingUntil=control['stagingUntil'],
                               annotationMode=control.get('annotationMode', 'view'), sourceDigest=control.get('sourceDigest'))
        control['expiresAt'] = result['expiresAt']
        control['stagingUntil'] = result['stagingUntil']
        control['cleanupAfter'] = result['stagingUntil']
        control['annotationsStorage'] = database.kind

    def _activate(self, control, job):
        share_id = control['shareId']
        try:
            self._not_retired(share_id)
            require(time.time() < job['stagingUntil'], 'Publication staging has expired', 'SHARE_EXPIRED')
            self._put_json('shares/' + share_id + '/control.json', control)
            self._put_json('jobs/' + share_id + '.json', job)
            if control.get('annotationsStorage'):
                self._annotations().call('activate', shareId=share_id)
        finally:
            # A cleanup which raced an upload may have removed its old job.
            # Keep the newly written copy cleanable without reviving access.
            if self.storage.get('retired/' + share_id) is not None:
                self._put_json('jobs/' + share_id + '.json', {**job, 'state': 'revoked', 'cleanupAfter': 0})
                self._not_retired(share_id)
        if control.get('annotationsStorage'):
            self.storage.delete_prefix('publication-intents/' + share_id + '.json')

    def _publication_document(self, document, share_id, mode):
        document = copy.deepcopy(document)
        for field in ('browserLinks', 'publicationApiBase', 'annotationAccess', 'publication', 'annotationsOpen'):
            document.pop(field, None)
        document['manifest'].pop('annotations', None)
        document['publication'] = {'shareId': share_id, 'revision': document['revision']}
        document['annotationAccess'] = {
            'endpoint': urlparse(self.public_url).path + '/s/' + share_id + '/api/annotations',
            'canRead': True, 'canAnnotate': mode == 'annotate', 'canManageAnnotations': False,
            'scope': 'share:' + share_id, 'author': {'name': '访客', 'verified': False},
        }
        return document

    def control(self, share_id):
        share_id = checked_id(share_id)
        self._not_retired(share_id)
        raw = self.storage.get('shares/' + share_id + '/control.json')
        require(raw is not None, '分享不存在或已删除', 'SHARE_UNAVAILABLE')
        control = json.loads(raw)
        from .cloud_database import cloud_enabled
        if cloud_enabled():
            from .cloud_assets import AssetDatabase
            registered = AssetDatabase().call('share_access', id=share_id)
            require((registered is None and not control.get('registered')) or
                    (registered is not None and registered['state'] == 'active'),
                    '分享已撤销或尚未完成', 'SHARE_EXPIRED')
        require(control['state'] == 'active' and
                (control['expiresAt'] is None or time.time() < control['expiresAt']),
                '分享已过期或已撤销', 'SHARE_EXPIRED')
        return control

    def quick_result(self, share_id, access_key, expiration):
        # A response may have been lost after the share became active. Return
        # the same link and key without storing the plaintext visitor key.
        from .cloud_database import cloud_enabled

        self._not_retired(share_id)
        raw = self.storage.get(f'shares/{share_id}/control.json')
        registered = None
        if cloud_enabled():
            from .cloud_assets import AssetDatabase
            registered = AssetDatabase().call('share_access', id=share_id)
            require(not registered or registered['state'] != 'revoked', 'Share was revoked', 'SHARE_EXPIRED')
        if raw is None or (registered and registered['state'] == 'uploading'):
            return None
        control = json.loads(raw)
        require(isinstance(access_key, str) and bool(ACCESS_KEY.fullmatch(access_key)) and
                hmac.compare_digest(key_digest(access_key, control['salt']), control['keyHash']),
                'Share retry uses another access key', 'REVISION_CONFLICT')
        require(control['state'] == 'active' and
                (control['expiresAt'] is None or time.time() < control['expiresAt']),
                'Share has expired or been revoked', 'SHARE_EXPIRED')
        require(not control.get('registered') or registered is not None, 'Share is unavailable', 'SHARE_UNAVAILABLE')
        job = self.storage.get(f'jobs/{share_id}.json')
        if job is None or json.loads(job)['state'] != 'active':
            return None
        if control.get('annotationsStorage'):
            # Object writes can finish before the final SQL activation reply.
            # Complete that same frozen claim before acknowledging its retry.
            self._annotations().call('activate', shareId=share_id)
            self._not_retired(share_id)
            self.storage.delete_prefix('publication-intents/' + share_id + '.json')
        return self._receipt(share_id, access_key, expiration, control['expiresAt'], control['revision'], control['pages'],
                             control.get('annotationMode', 'view'))

    def _receipt(self, share_id, access_key, expiration, expires, revision, pages, mode='view'):
        url = self.public_url + '/s/' + share_id + '/'
        return {'shareId': share_id, 'url': url, 'accessUrl': url + '#key=' + access_key,
                'accessKey': access_key, 'expiration': expiration, 'expiresAt': expires,
                'revision': revision, 'pages': pages, 'cleanupExecutor': self.executor,
                'annotationMode': mode}

    def _stage(self, share_id, job):
        self._not_retired(share_id)
        key = f'jobs/{share_id}.json'
        raw = self.storage.get(key)
        if raw is not None:
            previous = json.loads(raw)
            require(previous['revision'] == job['revision'], 'Share request targets another revision', 'REVISION_CONFLICT')
            require(previous['state'] in ('uploading', 'active'), 'Share was revoked', 'SHARE_EXPIRED')
            return {**previous, **job, 'expiresAt': previous['expiresAt'], 'stagingUntil': previous['stagingUntil'],
                    'cleanupAfter': previous['cleanupAfter']}
        self._put_json(key, job)
        return job

    def publish(self, service, board, expected_revision, expiration='7d', access_key=None, pages=None, *, share_id=None,
                annotation_mode='view'):
        mode = checked_annotation_mode(annotation_mode)
        require(expiration in EXPIRATIONS, 'expiration must be never, 7d or 30d', 'INVALID_ARGUMENT')
        access_key = access_key if access_key is not None else f'{secrets.randbelow(100000000):08d}'
        require(isinstance(access_key, str) and bool(ACCESS_KEY.fullmatch(access_key)),
                'accessKey must contain exactly eight ASCII digits', 'INVALID_ARGUMENT')
        versions = None
        if service.project_root:
            from .versions import Versions
            versions = Versions(service.store)
            require(versions.status(board)['publishedRevision'] == expected_revision,
                    'Publish the saved version before sharing it', 'REVISION_CONFLICT')
            doc = versions.read(board, expected_revision)
        else:
            doc = service.store.get(board, hydrate=False)
            require(doc['revision'] == expected_revision, 'Reload before sharing', 'REVISION_CONFLICT')
        documents = [(board, doc)]
        if pages is not None:
            require(service.project_root is not None and isinstance(pages, list),
                    'Multiple pages require a project and a page list', 'INVALID_ARGUMENT')
            assert versions is not None
            seen = {board}
            for page in pages:
                require(isinstance(page, dict) and isinstance(page.get('dashboardId'), str)
                        and type(page.get('expectedRevision')) is int,
                        'Each page requires dashboardId and expectedRevision', 'INVALID_ARGUMENT')
                page_id, revision = identifier(page['dashboardId']), page['expectedRevision']
                require(page_id not in seen, 'Duplicate page', 'INVALID_ARGUMENT')
                require(versions.status(page_id)['publishedRevision'] == revision,
                        'Publish each selected page before sharing it', 'REVISION_CONFLICT')
                documents.append((page_id, versions.read(page_id, revision)))
                seen.add(page_id)
        heartbeat = self.storage.get('cleaner-status.json')
        require(heartbeat is not None and time.time() - json.loads(heartbeat)['completedAt'] < 7 * 3600,
                'Confirm a successful six-hour cloud cleanup invocation before publishing',
                'CLOUD_CLEANER_UNAVAILABLE')
        self.storage.check_private()
        if share_id is not None:
            previous = self.quick_result(share_id, access_key, expiration)
            if previous is not None:
                return previous
        share_id = share_id or uuid.uuid4().hex
        if getattr(service.store, 'cos_enabled', False):
            return self._publish_cos(service, documents, expiration, access_key, share_id, mode)
        now = int(time.time())
        lifetime = EXPIRATIONS[expiration]
        expires = now + lifetime if lifetime is not None else None
        owner = hashlib.sha256(str(Path(service.project_root or service.store.root).resolve()).encode()).hexdigest()
        registered_pages = [{'id': page_id, 'revision': page_doc['revision']} for page_id, page_doc in documents]
        job = {'shareId': share_id, 'state': 'uploading', 'cleanupAfter': now + 3600,
               'stagingUntil': now + 3600, 'expiresAt': expires, 'owner': owner, 'dashboardId': board,
               'revision': doc['revision'], 'pages': registered_pages, 'annotationMode': mode}
        job = self._stage(share_id, job)
        expires = job['expiresAt']
        now = job['stagingUntil'] - 3600
        self._configure_annotations(job)
        self._put_json(f'jobs/{share_id}.json', job)
        registry = getattr(service.store, 'assets', None)
        if registry:
            registry.call('share_register', id=share_id, pages=registered_pages, state='uploading', expiresAt=expires)
        # Only SCF deletes remote content. The upload staging directory is
        # local temporary data and is removed even if export/upload fails.
        with tempfile.TemporaryDirectory(prefix='charts-share-') as temporary:
            from .deployment import export_site
            exported = export_site(service.store, board, output_root=Path(temporary), document=doc)['export']
            site = Path(exported['directory'])
            if len(documents) > 1:
                import os
                import shutil
                shards = {}
                for path in (site / 'data').iterdir():
                    if path.is_file():
                        shards[hashlib.sha256(path.read_bytes()).hexdigest()] = path
                entries = [{'id': board, 'title': doc['manifest']['title'], 'path': 'document.json', 'revision': doc['revision']}]
                for page_id, page_doc in documents[1:]:
                    page_export = export_site(service.store, page_id, output_root=Path(temporary), document=page_doc)['export']
                    page_site = Path(page_export['directory'])
                    target = site / 'pages' / page_id
                    target.mkdir(parents=True)
                    page_document = json.loads((page_site / 'document.json').read_bytes())
                    for dataset, paths in page_document['staticFiles'].items():
                        reused = []
                        for name in paths:
                            source = page_site / name
                            digest = hashlib.sha256(source.read_bytes()).hexdigest()
                            destination = shards.get(digest)
                            if destination is None:
                                destination = target / name
                                destination.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copyfile(source, destination)
                                shards[digest] = destination
                            reused.append(Path(os.path.relpath(destination, target)).as_posix())
                        page_document['staticFiles'][dataset] = reused
                    (target / 'document.json').write_text(json.dumps(page_document, ensure_ascii=False), encoding='utf-8')
                    entries.append({'id': page_id, 'title': page_doc['manifest']['title'],
                                    'path': 'pages/' + page_id + '/document.json', 'revision': page_doc['revision']})
                root_doc = json.loads((site / 'document.json').read_bytes())
                root_doc['staticPages'] = entries
                (site / 'document.json').write_text(json.dumps(root_doc, ensure_ascii=False), encoding='utf-8')
            else:
                entries = [{'id': board, 'title': doc['manifest']['title'], 'path': 'document.json', 'revision': doc['revision']}]
            for entry in entries:
                path = site / entry['path']
                path.write_bytes(json_bytes(self._publication_document(json.loads(path.read_bytes()), share_id, mode)))
            files = []
            for path in sorted(site.rglob('*')):
                if not path.is_file():
                    continue
                name = path.relative_to(site).as_posix()
                kind = mimetypes.guess_type(name)[0] or 'application/octet-stream'
                self.storage.put('shares/' + share_id + '/site/' + name, path.read_bytes(), kind)
                files.append(name)
            salt = secrets.token_hex(16)
            control = {'shareId': share_id, 'state': 'active', 'dashboardId': board,
                       'revision': doc['revision'], 'owner': owner, 'createdAt': now,
                       'expiresAt': expires, 'salt': salt, 'keyHash': key_digest(access_key, salt),
                       'files': files, 'pages': entries, 'registered': registry is not None,
                       'annotationMode': mode, 'annotationsStorage': job.get('annotationsStorage')}
            self._activate(control, {**job, 'state': 'active', 'cleanupAfter': expires, 'pages': entries})
            if registry:
                registry.call('share_register', id=share_id, pages=registered_pages, state='active',
                              expiresAt=expires, bytes=sum(path.stat().st_size for path in site.rglob('*') if path.is_file()))
        return self._receipt(share_id, access_key, expiration, expires, doc['revision'], entries, mode)

    def index_project(self, store):
        """Register old publications, including every page of a multi-page share."""
        owner = hashlib.sha256(str(store.project_root.resolve()).encode()).hexdigest()
        for key in self.storage.list('jobs/'):
            raw = self.storage.get(key)
            if raw is None:
                continue
            job = json.loads(raw)
            if job.get('owner') != owner:
                continue
            existing = store.assets.database.call('share_access', id=job['shareId'])
            if existing is not None:
                continue
            pages = job.get('pages') or [{'id': job['dashboardId'], 'revision': job['revision']}]
            # Listing metadata estimates current object bytes without reading business rows.
            size = self.storage.size_prefix('shares/' + job['shareId'] + '/')
            store.assets.call('share_register', id=job['shareId'], pages=pages, state=job['state'],
                              expiresAt=job['expiresAt'], bytes=size,
                              stagingUntil=job.get('stagingUntil', job.get('cleanupAfter')))

    def _publish_cos(self, service, documents, expiration, access_key, share_id, mode='view'):
        from .assets import DIST, FAVICON_LINK, require_preview
        from .cloud_assets import parquet_resources
        from .columnar import FORMAT, copy_package, export_format
        from .cos_view import web_document
        require_preview()
        _, binary = export_format('parquet')
        now = int(time.time())
        lifetime = EXPIRATIONS[expiration]
        expires = now + lifetime if lifetime is not None else None
        owner = hashlib.sha256(str(Path(service.project_root).resolve()).encode()).hexdigest()
        pages = [{'id': board, 'title': doc['manifest']['title'], 'revision': doc['revision'],
                  'path': 'document.json' if index == 0 else f'pages/{board}/document.json'}
                 for index, (board, doc) in enumerate(documents)]
        assets = service.store.assets
        job = {'shareId': share_id, 'state': 'uploading', 'cleanupAfter': now + 3600,
               'stagingUntil': now + 3600, 'expiresAt': expires, 'owner': owner, 'dashboardId': pages[0]['id'],
               'revision': pages[0]['revision'], 'pages': pages, 'annotationMode': mode}
        job = self._stage(share_id, job)
        expires = job['expiresAt']
        now = job['stagingUntil'] - 3600
        self._configure_annotations(job)
        self._put_json(f'jobs/{share_id}.json', job)
        assets.call('share_register', id=share_id, pages=pages, state='uploading', expiresAt=expires,
                    stagingUntil=job['stagingUntil'])
        files, asset_files, total = [], {}, 0
        datasets, converted = {}, set()
        def put(name, raw, kind):
            nonlocal total
            self.storage.put('shares/' + share_id + '/site/' + name, raw, kind)
            files.append(name)
            total += len(raw)

        def dataset_asset(ref):
            version = ref['version']
            if version in datasets:
                return datasets[version]
            obj = assets.call('object_get', version=version)
            if obj is None:
                raise DashboardError('ASSET_UNAVAILABLE', 'Dataset files unavailable')
            descriptor = obj['descriptor']
            require(descriptor['metadata'] == ref, 'Remote data metadata differs', 'DATA_CONFLICT')
            if descriptor.get('dataFormat') != FORMAT:
                # Keep old immutable objects and their existing publications.
                # A new share owns this conversion and its ordinary cleanup job.
                with tempfile.TemporaryDirectory(prefix='charts-share-data-') as temporary:
                    directory = Path(temporary)
                    receipt = copy_package(
                        directory, service.store.data, ref, service.store.runtime_root / 'parquet-cache', binary,
                        partition_field=descriptor.get('partitionIndex', {}).get('field'), include_options=True,
                    )
                    resources = parquet_resources(receipt)
                    filenames = [*resources['shards'],
                                 *(name for group in resources['options'].values() for name in group['files'])]
                    for name in filenames:
                        put(f"data/{obj['id']}/{name}", (directory / name).read_bytes(), 'application/octet-stream')
                obj = {**obj, 'descriptor': {**descriptor, **resources}}
                converted.add(obj['id'])
            datasets[version] = obj
            return obj

        for index, ((board, doc), page) in enumerate(zip(documents, pages)):
            def url_for(object_id, name):
                path = f'data/{object_id}/{name}'
                if object_id not in converted:
                    asset_files[path] = {'object': object_id, 'name': name, 'board': board, 'revision': doc['revision']}
                return path if index == 0 else '../../' + path
            web = web_document(service.store, doc, url_for, dataset_asset=dataset_asset)
            web = self._publication_document(web, share_id, mode)
            if index == 0:
                web['staticPages'] = pages
            put(page['path'], json.dumps(web, ensure_ascii=False).encode(), 'application/json')
        for name in ('app.js', 'app.css', 'static-worker.js'):
            put(name, (DIST / name).read_bytes(), 'text/css' if name.endswith('.css') else 'text/javascript')
        put('index.html', ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' + FAVICON_LINK + '<link rel="stylesheet" href="app.css"></head><body><div id="root"></div><script>window.__chartsBoot={mode:"static"}</script><script src="app.js"></script></body></html>').encode(), 'text/html')
        salt = secrets.token_hex(16)
        control = {**job, 'state': 'active', 'createdAt': now, 'salt': salt,
                   'keyHash': key_digest(access_key, salt), 'files': files + list(asset_files),
                   'assetFiles': asset_files, 'project': service.store.project, 'registered': True}
        self._activate(control, {**job, 'state': 'active', 'cleanupAfter': expires})
        assets.call('share_register', id=share_id, pages=pages, state='active', expiresAt=expires, bytes=total)
        return self._receipt(share_id, access_key, expiration, expires, pages[0]['revision'], pages, mode)

    def import_site(self, archive, source_key, request_id, *, secret, annotation_mode='view', expiration='7d',
                    access_key=None):
        """Publish a frozen local ZIP into the existing service, without an author workspace import."""
        import zipfile
        from .assets import DIST, FAVICON_LINK, require_preview
        require_preview()
        mode = checked_annotation_mode(annotation_mode)
        require(expiration in EXPIRATIONS, 'Invalid expiration', 'INVALID_ARGUMENT')
        require(isinstance(source_key, str) and re.fullmatch(r'[0-9a-f]{64}', source_key),
                'Invalid author project identity', 'INVALID_ARGUMENT')
        require(isinstance(request_id, str) and 1 <= len(request_id) <= 128,
                'requestId is required', 'INVALID_ARGUMENT')
        require(isinstance(secret, bytes) and len(secret) >= 32, 'Stable server secret required', 'INVALID_CONFIG')
        identity = json_bytes([source_key, request_id])
        share_id = hmac.new(secret, b'local-publication:' + identity, hashlib.sha256).hexdigest()[:32]
        self._not_retired(share_id)
        derived = hmac.new(secret, b'local-publication-key:' + identity, hashlib.sha256).digest()
        access_key = access_key if access_key is not None else f'{int.from_bytes(derived, "big") % 100000000:08d}'
        require(isinstance(access_key, str) and ACCESS_KEY.fullmatch(access_key), 'Invalid access key', 'INVALID_ARGUMENT')
        try:
            package = zipfile.ZipFile(archive)
        except (OSError, zipfile.BadZipFile) as error:
            raise DashboardError('INVALID_ARGUMENT', 'Invalid publication ZIP') from error
        with package:
            entries = package.infolist()
            require(len(entries) <= 10000 and sum(item.file_size for item in entries) <= 512 * 1024 * 1024,
                    'Publication package exceeds the 512 MiB limit', 'PAYLOAD_TOO_LARGE')
            files = {}
            for item in entries:
                path = PurePosixPath(item.filename)
                require(not path.is_absolute() and '..' not in path.parts and '\\' not in item.filename
                        and str(path) == item.filename.rstrip('/') and item.filename not in files
                        and (item.external_attr >> 16) & 0o170000 != 0o120000,
                        'Invalid publication file path', 'INVALID_ARGUMENT')
                if item.is_dir():
                    continue
                require(item.file_size <= 64 * 1024 * 1024, 'Publication file is too large', 'PAYLOAD_TOO_LARGE')
                require(item.filename in ('index.html', 'app.js', 'app.css', 'static-worker.js', 'document.json',
                                           'export-manifest.json', 'README.txt') or
                        (path.parts[0] in ('data', 'pages') and path.suffix in ('.json', '.gz', '.parquet')),
                        'Unsupported publication resource', 'INVALID_ARGUMENT')
                files[item.filename] = item
            require('document.json' in files and 'export-manifest.json' in files,
                    'Export a complete static site first', 'INVALID_ARGUMENT')
            fingerprint = hashlib.sha256()
            fingerprint.update(json_bytes([mode, expiration, access_key]))
            for name in sorted(files):
                fingerprint.update(json_bytes([name, hashlib.sha256(package.read(name)).hexdigest()]))
            digest = fingerprint.hexdigest()
            document = json.loads(package.read('document.json'))
            manifest = json.loads(package.read('export-manifest.json'))
            require(isinstance(document, dict) and document.get('schemaVersion') == 2 and
                    isinstance(document.get('manifest'), dict) and isinstance(document['manifest'].get('components'), dict),
                    'Invalid publication document', 'INVALID_ARGUMENT')
            board = identifier(document.get('id'))
            revision = document.get('revision')
            require(type(revision) is int and revision >= 1 and manifest.get('revision') == revision
                    and manifest.get('dashboardId') == board, 'Export version does not match document', 'REVISION_CONFLICT')
            # A package from the local author exports one selected saved version.
            require(not document.get('staticPages'), 'Import one saved page per request', 'INVALID_ARGUMENT')
            require(isinstance(document.get('staticFiles'), dict), 'Static data files required', 'INVALID_ARGUMENT')
            used = set()
            for names in document['staticFiles'].values():
                require(isinstance(names, list), 'Invalid static data manifest', 'INVALID_ARGUMENT')
                for name in names:
                    require(isinstance(name, str) and name.startswith('data/') and name in files,
                            'A published data resource is missing', 'INVALID_ARGUMENT')
                    used.add(name)
            # export_site does not emit remote options/partitions; reject their
            # URLs instead of allowing an imported page to depend on an author host.
            require(not document.get('staticOptions') and not document.get('staticPartitionIndexes'),
                    'Local export must contain self-contained data shards', 'INVALID_ARGUMENT')
            pages = [{'id': board, 'title': document['manifest'].get('title', board),
                      'path': 'document.json', 'revision': revision}]
            old = self.storage.get('jobs/' + share_id + '.json')
            if old is not None:
                previous = json.loads(old)
                require(previous.get('owner') == source_key and previous.get('sourceDigest') == digest,
                        'requestId already identifies another publication', 'REVISION_CONFLICT')
                result = self.quick_result(share_id, access_key, expiration)
                if result is not None:
                    return result
            heartbeat = self.storage.get('cleaner-status.json')
            require(heartbeat is not None and time.time() - json.loads(heartbeat)['completedAt'] < 7 * 3600,
                    'Confirm a successful cloud cleanup invocation before publishing', 'CLOUD_CLEANER_UNAVAILABLE')
            self.storage.check_private()
            now = int(time.time())
            lifetime = EXPIRATIONS[expiration]
            job = {
                'shareId': share_id, 'state': 'uploading', 'owner': source_key, 'dashboardId': board,
                'revision': revision, 'pages': pages, 'annotationMode': mode, 'sourceDigest': digest,
                'expiresAt': now + lifetime if lifetime is not None else None,
                'cleanupAfter': now + 3600, 'stagingUntil': now + 3600,
            }
            # The same transaction claims the request fingerprint even for a
            # viewing-only import, so concurrent retries cannot change its copy.
            # The tiny intent precedes the SQL claim: a crash between claiming
            # the request and writing its full job must still be cleanable.
            self._configure_annotations(job, force=True)
            job = self._stage(share_id, job)
            self._put_json('jobs/' + share_id + '.json', job)
            uploaded = []

            def put(name, raw):
                self.storage.put('shares/' + share_id + '/site/' + name, raw,
                                 mimetypes.guess_type(name)[0] or 'application/octet-stream')
                uploaded.append(name)

            for name in sorted(used):
                put(name, package.read(name))
            # Use the already-deployed shared UI, never executable code supplied
            # in an upload. Business HTML components retain their iframe sandbox.
            for name in ('app.js', 'app.css', 'static-worker.js'):
                put(name, (DIST / name).read_bytes())
            for field in ('sources', 'queries', 'annotations'):
                document['manifest'].pop(field, None)
            document = self._publication_document(document, share_id, mode)
            document['snapshot'] = {'datasets': {}}
            put('document.json', json_bytes(document))
            put('index.html', ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">' + FAVICON_LINK +
                '<link rel="stylesheet" href="app.css"></head><body><div id="root"></div>'
                '<script>window.__chartsBoot={mode:"static"}</script><script src="app.js"></script></body></html>').encode())
            salt = secrets.token_hex(16)
            control = {**job, 'state': 'active', 'files': uploaded, 'registered': False,
                       'createdAt': job['stagingUntil'] - 3600, 'salt': salt, 'keyHash': key_digest(access_key, salt)}
            self._activate(control, {**job, 'state': 'active', 'cleanupAfter': job['expiresAt']})
            return self._receipt(share_id, access_key, expiration, job['expiresAt'], revision, pages, mode)

    def authenticate(self, share_id, key):
        control = self.control(share_id)
        require(isinstance(key, str) and bool(ACCESS_KEY.fullmatch(key)) and
                hmac.compare_digest(key_digest(key, control['salt']), control['keyHash']),
                '访问密钥错误', 'INVALID_ACCESS_KEY')
        return control

    def publication_page(self, share_id, board=None, *, control=None) -> dict:
        control = control or self.control(share_id)
        board = identifier(board or control['dashboardId'])
        page = next((page for page in control['pages'] if page['id'] == board), None)
        if page is None:
            raise DashboardError('FORBIDDEN', '此分享不包含该页面')
        return page

    def annotations(self, share_id, board=None):
        control = self.control(share_id)
        page = self.publication_page(share_id, board, control=control)
        notes = (self._annotations().call('read', shareId=share_id, dashboardId=page['id'])
                 if control.get('annotationMode') == 'annotate' else [])
        # Recheck after storage access: a revocation during a slow read must not
        # turn into a successful response containing previously protected data.
        self.control(share_id)
        return {'shareId': share_id, 'dashboardId': page['id'], 'revision': page['revision'],
                'annotations': notes, 'count': len(notes), 'independentSave': True,
                'canAnnotate': control.get('annotationMode') == 'annotate',
                'canManageAnnotations': False, 'author': {'name': '访客', 'verified': False}}

    def append_annotation(self, share_id, board, note, author_name=None):
        control = self.control(share_id)
        require(control.get('annotationMode') == 'annotate', '此分享仅允许查看', 'FORBIDDEN')
        page = self.publication_page(share_id, board, control=control)
        require(isinstance(note, dict), 'Annotation must be an object', 'INVALID_ARGUMENT')
        clean = {key: copy.deepcopy(note[key]) for key in ('id', 'componentId', 'text', 'createdAt', 'anchor', 'view')
                 if key in note}
        validate_annotations([clean])
        require('anchor' in clean, '位置批注必须提供锚点', 'INVALID_ARGUMENT')
        require(author_name is None or isinstance(author_name, str) and len(author_name) <= 80,
                '署名最多 80 字', 'INVALID_ARGUMENT')
        require(len(json_bytes(clean)) <= 32 * 1024, 'Annotation is too large', 'PAYLOAD_TOO_LARGE')
        document = json.loads(self.content(share_id, page['path'], control=control))
        component = clean.get('componentId')
        require(component is None or component in document['manifest']['components'],
                '此位置不属于分享版本', 'INVALID_ARGUMENT')
        view = clean.get('view', {})
        require(isinstance(view, dict), 'Invalid annotation view', 'INVALID_ARGUMENT')
        require(view.get('revision', page['revision']) == page['revision'],
                '批注必须针对当前分享版本', 'REVISION_CONFLICT')
        clean['author'] = {'name': (author_name or '').strip() or '访客', 'verified': False}
        fingerprint = hashlib.sha256(json.dumps(clean, ensure_ascii=False, sort_keys=True,
                                                separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        clean['context'] = {'shareId': share_id, 'designRevision': page['revision'],
                            'filters': copy.deepcopy(view.get('filters', []))}
        clean['receivedAt'] = utcnow()
        saved = self._annotations().call('append', shareId=share_id, dashboardId=page['id'],
                                         annotation=clean, fingerprint=fingerprint)
        self.control(share_id)
        return {'shareId': share_id, 'dashboardId': page['id'], 'revision': page['revision'],
                'annotation': saved, 'independentSave': True}

    def owner_control(self, share_id, source_key):
        control = self.control(share_id)
        require(isinstance(source_key, str) and hmac.compare_digest(control['owner'], source_key),
                'Share belongs to another author project', 'FORBIDDEN')
        return control

    def revoke_owner(self, share_id, source_key):
        control = self.owner_control(share_id, source_key)
        return self._revoke_control(control)

    def _revoke_control(self, control):
        share_id = control['shareId']
        job = {'shareId': share_id, 'state': 'revoked', 'expiresAt': control['expiresAt'],
               'cleanupAfter': int(time.time()), 'owner': control['owner'], 'dashboardId': control['dashboardId'],
               'revision': control['revision'], 'annotationMode': control.get('annotationMode', 'view'),
               'annotationsStorage': control.get('annotationsStorage')}
        self._put_json('jobs/' + share_id + '.json', job)
        if control.get('annotationsStorage'):
            self._annotations().call('revoke', shareId=share_id)
        retire_id(self.storage, share_id)
        self._put_json('shares/' + share_id + '/control.json', {**control, 'state': 'revoked'})
        return {'shareId': share_id, 'revoked': True, 'cleanupState': 'pending', 'cleanupExecutor': self.executor}

    def replace(self, service, board, share_id, expected_revision, expiration='7d'):
        """Finish the new publication before revoking the selected old link."""
        previous = self.control(share_id)
        owner = hashlib.sha256(str(Path(service.project_root or service.store.root).resolve()).encode()).hexdigest()
        require(previous['owner'] == owner and previous['dashboardId'] == board,
                'Share belongs to another project/dashboard', 'FORBIDDEN')
        access_key = f'{secrets.randbelow(100000000):08d}'
        while hmac.compare_digest(key_digest(access_key, previous['salt']), previous['keyHash']):
            access_key = f'{secrets.randbelow(100000000):08d}'
        pages = []
        if len(previous.get('pages', [])) > 1:
            from .versions import Versions
            versions = Versions(service.store)
            for page in previous['pages'][1:]:
                revision = versions.status(page['id'])['publishedRevision']
                require(revision is not None, 'Publish each selected page before sharing it', 'REVISION_CONFLICT')
                pages.append({'dashboardId': page['id'], 'expectedRevision': revision})
        result = self.publish(service, board, expected_revision, expiration, access_key, pages,
                              annotation_mode=previous.get('annotationMode', 'view'))
        try:
            job_key = 'jobs/' + result['shareId'] + '.json'
            raw = self.storage.get(job_key)
            require(raw is not None, 'New share job is missing', 'NOT_FOUND')
            assert raw is not None
            self._put_json(job_key, {**json.loads(raw), 'replacesShareId': share_id})
            self.revoke(service, board, share_id)
        except Exception as error:
            # Return the new credentials even if revocation fails; retry only
            # the old ID rather than creating another publication.
            return {**result, 'previousShareId': share_id, 'previousRevoked': False,
                    'followUp': 'dashboard_share_delete',
                    'warning': {'code': 'PREVIOUS_SHARE_REVOKE_FAILED', 'type': type(error).__name__}}
        return {**result, 'previousShareId': share_id, 'previousRevoked': True}

    def content(self, share_id, name, *, control=None) -> bytes:
        # The gateway may reuse the control checked earlier in this request.
        control = self.control(share_id) if control is None else control
        path = PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts and name in control['files'],
                '分享文件不存在', 'NOT_FOUND')
        if name in control.get('assetFiles', {}):
            from .cloud_assets import CloudAssets
            assets = CloudAssets(control['project'])
            entry = control['assetFiles'][name]
            obj = assets.call('object_get', id=entry['object'])
            require(obj is not None, '分享数据已删除', 'SHARE_UNAVAILABLE')
            return assets.read_file(obj, entry['name'])
        raw = self.storage.get('shares/' + checked_id(share_id) + '/site/' + name)
        if raw is None:
            raise DashboardError('NOT_FOUND', '分享文件不存在')
        return raw

    def revoke(self, service, board, share_id):
        control = self.control(share_id)
        owner = hashlib.sha256(str(Path(service.project_root or service.store.root).resolve()).encode()).hexdigest()
        require(control['owner'] == owner and control['dashboardId'] == board,
                'Share belongs to another project/dashboard', 'FORBIDDEN')
        if getattr(service.store, 'assets', None):
            self.index_project(service.store)
            service.store.assets.call('share_revoke', id=share_id)
        return self._revoke_control(control)

    def status(self, service, board, share_id=None):
        if share_id is not None:
            checked_id(share_id)
        owner = hashlib.sha256(str(Path(service.project_root or service.store.root).resolve()).encode()).hexdigest()
        keys = ['jobs/' + share_id + '.json'] if share_id else list(self.storage.list('jobs/'))
        shares = []
        for key in keys:
            raw = self.storage.get(key)
            if raw is None:
                continue
            job = json.loads(raw)
            if job.get('owner') != owner or job.get('dashboardId') != board:
                continue
            due = job['cleanupAfter'] is not None and time.time() >= job['cleanupAfter']
            shares.append({'shareId': job['shareId'], 'state': 'expired' if due and job['state'] == 'active' else job['state'],
                           'revision': job['revision'], 'expiresAt': job['expiresAt'], 'pages': job.get('pages', []),
                           'annotationMode': job.get('annotationMode', 'view'),
                           'replacesShareId': job.get('replacesShareId'),
                           'cleanupState': 'pending' if due else 'scheduled' if job['cleanupAfter'] else 'not_scheduled',
                           'url': self.public_url + '/s/' + job['shareId'] + '/'})
        return {'shares': shares, 'cleanupExecutor': self.executor}


def cleanup_due(storage, now=None):
    """Called by the SCF timer, never scheduled by a local MCP or web server."""
    from .cloud_assets import AssetDatabase
    now = time.time() if now is None else now
    removed, failed = 0, []
    handled = set()
    # Imports claim their request in SQL before recording the complete job.
    # An intent makes that otherwise jobless crash window recoverable. The
    # same SQL/SQLite transaction that activates a scope decides whether this
    # stale intent may retire it, so an active copy cannot be swept by mistake.
    from .share_annotations import annotation_store
    for key in list(storage.list('publication-intents/')):
        try:
            raw = storage.get(key)
            if raw is None:
                continue
            intent = json.loads(raw)
            share_id = checked_id(intent['shareId'])
            handled.add(share_id)
            require(key == 'publication-intents/' + share_id + '.json', 'Invalid publication intent', 'INVALID_ARGUMENT')
            if intent['cleanupAfter'] > now and storage.get('retired/' + share_id) is None:
                continue
            from .cloud_database import cloud_enabled
            if cloud_enabled() or (os.environ.get('CHARTS_STORAGE_BACKEND') != 'cloudflare' and os.environ.get('CLOUDBASE_API_KEY')):
                registered = AssetDatabase().call('share_access', id=share_id)
                if registered and not AssetDatabase().call('share_cleanup_claim', registered['project'],
                                                          id=share_id, now=int(now)):
                    continue
            claim = annotation_store(storage).call('cleanup_claim', shareId=share_id, now=int(now))
            if not claim['claimed']:
                if claim['state'] == 'active':
                    storage.delete_prefix(key)
                else:
                    storage.put(key, json_bytes({**intent, 'cleanupAfter': claim['stagingUntil']}), 'application/json')
                continue
            retire_id(storage, share_id)
            storage.delete_prefix('shares/' + share_id + '/')
            storage.delete_prefix('jobs/' + share_id + '.json')
            storage.delete_prefix(key)
            removed += 1
        except Exception as error:
            failed.append({'job': key, 'type': type(error).__name__})
    # Snapshot only the small job-key list; objects are deleted in bounded pages.
    for key in list(storage.list('jobs/')):
        try:
            raw = storage.get(key)
            if raw is None:
                continue
            job = json.loads(raw)
            share_id = checked_id(job['shareId'])
            handled.add(share_id)
            require(key == 'jobs/' + share_id + '.json', 'Invalid cleanup job', 'INVALID_ARGUMENT')
            deadline = job['cleanupAfter']
            registered = None
            from .cloud_database import cloud_enabled
            if cloud_enabled() or (os.environ.get('CHARTS_STORAGE_BACKEND') != 'cloudflare' and os.environ.get('CLOUDBASE_API_KEY')):
                registered = AssetDatabase().call('share_access', id=share_id)
                if registered and registered['state'] == 'uploading':
                    deadline = registered['stagingUntil']
                elif registered and registered['state'] == 'revoked':
                    deadline = 0
                elif registered and registered['state'] == 'active':
                    deadline = registered['expiresAt']
            retired = storage.get('retired/' + share_id) is not None
            if retired:
                deadline = 0
                if registered and registered['state'] != 'revoked':
                    AssetDatabase().call('share_revoke', registered['project'], id=share_id)
                    registered = {**registered, 'state': 'revoked'}
            if deadline is None or deadline > now:
                continue
            if registered:
                claimed = AssetDatabase().call('share_cleanup_claim', registered['project'],
                                               id=share_id, now=int(now))
                if not claimed:
                    continue
            if job.get('annotationsStorage'):
                claimed = annotation_store(storage).call('cleanup_claim', shareId=share_id, now=int(now),
                    revoked=retired or job['state'] == 'revoked' or bool(registered and registered['state'] == 'revoked'))
                if not claimed['claimed']:
                    continue
            retire_id(storage, share_id)
            storage.delete_prefix('shares/' + share_id + '/')
            if job.get('annotationsStorage') == 'postgres-v1':
                from .share_annotations import ShareAnnotationDatabase
                ShareAnnotationDatabase().call('delete', shareId=share_id)
            # Delete access metadata, job and their historical versions only
            # after every content object has been physically deleted.
            storage.delete_prefix('jobs/' + share_id + '.json')
            removed += 1
        except Exception as error:
            # Preserve failed jobs for the next cloud invocation. Never log
            # remote payloads, access codes or credential-bearing SDK messages.
            failed.append({'job': key, 'type': type(error).__name__})
    # An upload already in flight can write again after its job was removed,
    # then crash before finalization recreates that job. Permanent opaque IDs
    # let the existing timer sweep such late files without an author process.
    # This scan runs only during cleanup, never while appending an annotation.
    for key in storage.list('retired/'):
        try:
            share_id = checked_id(key.removeprefix('retired/'))
            require(key == 'retired/' + share_id, 'Invalid retired share ID', 'INVALID_ARGUMENT')
            if share_id in handled:
                continue
            prefix = 'shares/' + share_id + '/'
            if next(iter(storage.list(prefix)), None) is not None:
                storage.delete_prefix(prefix)
                removed += 1
        except Exception as error:
            failed.append({'job': key, 'type': type(error).__name__})
    return {'removed': removed, 'failed': failed}
