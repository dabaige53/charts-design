"""Project operations with PostgreSQL as the authoritative state."""
from __future__ import annotations

import copy
import difflib
import json
from pathlib import Path
import uuid

from .cloud_database import CloudDatabase
from .cloud_data import CloudData
from .model import (DashboardError, apply_operations, identifier, json_bytes,
                    new_document, require, utcnow, validate, validate_component_content)
from .project import DEFAULTS
from .store import Store


class CloudProjectStore(Store):
    def __init__(self, project_root, runtime_root, database=None):
        self.project_root = Path(project_root).expanduser().resolve()
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.root = self.project_root / 'dashboards'
        self.root.mkdir(parents=True, exist_ok=True)
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.project = self.project_root.name
        self.database = database or CloudDatabase()
        self.config = self.database.call('ensure', self.project, config=DEFAULTS)
        from .cloud_assets import CloudAssets
        self.assets = CloudAssets(self.project)
        self.cos_enabled = self.config.get('storageFormat') == 'cos-v1'
        self.data = CloudData(self.runtime_root / 'data-cache', self.database, self.project,
                              self.assets, self.cos_enabled)
        self.data.partition_fields = self.config.get('storage', {}).get('partitionFields', [])
        from .local_view import LocalView
        self.prepared_views = LocalView(self.data)

    def _encode(self, doc, previous=None):
        if not self.cos_enabled:
            return doc
        from .statistical import statistical_artifacts
        changed = None
        if previous and previous.get('computed'):
            old, new = previous['manifest'], doc['manifest']
            same_inputs = all(old.get(key) == new.get(key) for key in ('metrics', 'datasets', 'filters')) and all(
                previous['snapshot'].get(key) == doc['snapshot'].get(key) for key in ('datasetRefs', 'componentDataRefs'))
            if same_inputs:
                changed = [key for key, component in new['components'].items() if component != old['components'].get(key)]
        prepared = self.prepared_views.prepare(doc, component_ids=changed, include_filter_options=False)
        computed = prepared['computed']
        if previous is not None and changed is not None:
            for group in ('components', 'tables', 'grouped'):
                computed[group] = {**{key: value for key, value in previous['computed'].get(group, {}).items()
                                     if key in doc['manifest']['components'] and key not in changed},
                                   **computed[group]}
        doc = {**doc, 'computed': computed,
               'statisticalArtifacts': statistical_artifacts(self.statistical_document(doc))}
        return self.assets.save_document(doc)

    def _decode(self, doc):
        if doc and 'cosObject' in doc:
            self.cos_enabled = self.data.cos_enabled = True
        return self.assets.hydrate_document(doc)

    def connect(self):
        raise DashboardError('UNSUPPORTED_OPERATION', 'Cloud projects use PostgreSQL transactions')

    def compatible(self, document):
        return document

    def create(self, board_id, title, document=None):
        identifier(board_id)
        doc = json.loads(json_bytes(document or new_document(board_id, title)))
        doc['id'], doc['revision'] = board_id, 1
        validate(doc)
        for key, component in doc['manifest']['components'].items():
            validate_component_content(component, key)
        doc = self.compact(doc)
        notes = doc['manifest'].setdefault('annotations', [])
        self._note_context(doc, notes, [], preserve_incoming=document is not None)
        return self._decode(self.database.call('create', self.project, board=board_id,
                                              document=self._encode(doc), at=utcnow()))

    def get(self, board_id, hydrate=True):
        identifier(board_id)
        return self._decode(self.database.call('get', self.project, board=board_id))

    def readable(self, board):
        doc = self.database.call('readable', self.project, board=board)
        require(doc is not None, '暂无已保存版本', 'NO_SAVED_VERSION')
        return self._decode(doc)

    def display_revision(self, board):
        return self.readable(board)['revision']

    def revision(self, board_id):
        return self.get(board_id)['revision']

    def list(self):
        return self.database.call('list', self.project)

    @staticmethod
    def _note_context(doc, notes, previous, preserve_incoming=False):
        from .annotations import preserve_content_version
        old = {n['id']: n for n in previous}
        for note in notes:
            preserve_content_version(note, old.get(note['id']))
            if note['id'] in old:
                note['context'] = copy.deepcopy(old[note['id']].get('context', {}))
            elif not (preserve_incoming and isinstance(note.get('context'), dict)):
                note['context'] = {'designRevision': doc['revision'],
                                   'dataVersions': doc['snapshot'].get('datasetRefs', {}),
                                   'filters': doc['manifest']['filters']}

    def mutate(self, board_id, expected_revision, operations=None, restore_revision=None,
               use_current_data=False, expected_annotations=None):
        if operations and any(isinstance(op, dict) and op.get('op') == 'set_annotations' for op in operations):
            require(expected_annotations is not None, 'Read comments and provide expectedAnnotations before replacing them',
                    'ANNOTATION_CONFLICT')
        current = self.get(board_id)
        require(current['revision'] == expected_revision, 'Reload before editing', 'REVISION_CONFLICT')
        previous_notes = current['manifest'].get('annotations', [])
        if expected_annotations is not None:
            require(restore_revision is None and operations and
                    all(op.get('op') == 'set_annotations' for op in operations),
                    'Independent annotation saves may only replace annotations')
            require(previous_notes == expected_annotations, 'Reload annotations', 'ANNOTATION_CONFLICT')
        if restore_revision is not None:
            from .versions import Versions
            doc = Versions(self).read(board_id, restore_revision)
            doc['manifest']['annotations'] = copy.deepcopy(previous_notes)
            if use_current_data:
                doc['snapshot'] = copy.deepcopy(current['snapshot'])
        else:
            require(isinstance(operations, list), 'operations must be an array')
            assert isinstance(operations, list)
            doc = apply_operations(current, operations)
            if not any(op['op'] == 'set_annotations' for op in operations):
                doc['manifest']['annotations'] = copy.deepcopy(previous_notes)
        doc['revision'] = expected_revision
        doc = self.compact(doc)
        comparable = {key: value for key, value in current.items() if key != 'computed'}
        if doc == comparable:
            return current
        if expected_annotations is None:
            doc['revision'] += 1
        self._note_context(doc, doc['manifest'].get('annotations', []), previous_notes)
        return self._decode(self.database.call('commit', self.project, board=board_id, expected=expected_revision,
                                  document=self._encode(doc, current), previousNotes=previous_notes, at=utcnow(),
                                  restore=restore_revision is not None, revision=restore_revision))

    def annotation_command(self, board_id, revision, command):
        from .annotations import validate_command
        validate_command(command)
        database = CloudDatabase()
        database.url = database.url.rsplit('/', 1)[0] + '/charts_annotation'
        return database.call('apply', self.project, board=board_id, revision=revision, command=command, at=utcnow())

    def begin(self, board, expected):
        return self.database.call('begin', self.project, board=board, expected=expected, batch=uuid.uuid4().hex)

    def checkpoint(self, board, expected, name='', published=False, batch_id=None):
        self.database.call('checkpoint', self.project, board=board, expected=expected,
                           name=name, protected=published, batch=batch_id, at=utcnow(),
                           keep=self.config['history']['keepCheckpoints'])
        return {'dashboardId': board, 'revision': expected, 'name': name, 'published': published}

    def history(self, board_id, offset=0, limit=50):
        require(type(offset) is int and offset >= 0 and type(limit) is int and 0 < limit <= 10000,
                'Invalid history pagination')
        return self.database.call('history', self.project, board=board_id, offset=offset, limit=limit)

    def label_checkpoint(self, board, expected, revision, name, published=False):
        require(bool(name.strip()) or published, 'A name or protected marker is required')
        self.database.call('label', self.project, board=board, expected=expected,
                           revision=revision, name=name, protected=published)
        return {'revision': revision, 'name': name, 'published': published}

    def diff(self, board, first, second):
        docs = []
        for revision in (first, second):
            current = self.get(board)
            docs.append(current if current['revision'] == revision else
                        self._decode(self.database.call('revision_get', self.project, board=board, revision=revision)))
        from .semantic_diff import semantic_diff
        lines = [json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2).splitlines() for doc in docs]
        return {'diff': '\n'.join(difflib.unified_diff(*lines, fromfile=str(first), tofile=str(second))),
                'semanticChanges': semantic_diff(*docs)}

    def migrate(self, board_id, expected_revision):
        raise DashboardError('ALREADY_MIGRATED', 'Cloud projects already use durable data versions')

    def rollback_migration(self, board_id, expected_revision, backup_id):
        raise DashboardError('UNSUPPORTED_OPERATION', 'Local SQLite migration backups are not cloud revisions')
