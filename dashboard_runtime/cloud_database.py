"""CloudBase PostgreSQL access through its shared-instance HTTP gateway."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import TYPE_CHECKING

from .model import DashboardError, require

if TYPE_CHECKING:
    from psycopg_pool import ConnectionPool


_VIEW_CONNECTIONS: ContextVar[ConnectionPool | None] = ContextVar('neon_view_connections', default=None)
_POOLED_VIEW_ACTIONS = frozenset({
    'annotation_read', 'annotation_write', 'annotation_append', 'display_revision', 'generations_match',
})


_ANNOTATION_READ = """
    WITH current AS MATERIALIZED (SELECT public.charts_runtime('get', %s, %s) AS doc)
    SELECT jsonb_build_object(
        'id', doc->'id', 'revision', doc->'revision', 'title', doc#>'{manifest,title}',
        'annotations', doc#>'{manifest,annotations}', 'viewMode', doc#>'{manifest,viewMode}',
        'filters', doc#>'{manifest,filters}',
        'datasetRefs', coalesce(doc#>'{snapshot,datasetRefs}', '{}'::jsonb),
        'components', CASE WHEN %s AND doc#>'{manifest,components}' IS NOT NULL THEN
            coalesce((SELECT jsonb_object_agg(key, jsonb_build_object('title', value->'title', 'kind', value->'kind'))
                      FROM jsonb_each(doc#>'{manifest,components}')), '{}'::jsonb) END)
    FROM current
"""
_ANNOTATION_WRITE = """
    WITH current AS MATERIALIZED (SELECT public.charts_runtime('get', %s, %s) AS doc),
    saved AS MATERIALIZED (
        SELECT public.charts_runtime('commit', %s,
            %s || jsonb_build_object('document', jsonb_set(doc, '{manifest,annotations}', %s))) AS doc
        FROM current)
    SELECT jsonb_build_object('dashboardId', doc->'id', 'revision', doc->'revision',
                              'annotations', doc#>'{manifest,annotations}') FROM saved
"""
_ANNOTATION_APPEND = """
    WITH current AS MATERIALIZED (SELECT public.charts_runtime('get', %(project)s, %(board)s) AS doc),
    state AS (
        SELECT doc->'revision' AS revision, doc#>'{manifest,annotations}' AS notes,
            doc#>'{manifest,components}' AS components, doc,
            %(note)s::jsonb || jsonb_build_object('context', jsonb_build_object(
                'designRevision', doc->'revision',
                'dataVersions', coalesce(doc#>'{snapshot,datasetRefs}', '{}'::jsonb),
                'filters', coalesce(nullif(doc#>'{manifest,filters}', 'null'::jsonb),
                                    %(note)s::jsonb#>'{view,filters}', '[]'::jsonb))) AS note
        FROM current),
    merged AS MATERIALIZED (
        SELECT *, (SELECT item FROM jsonb_array_elements(notes) AS item
                   WHERE item->>'id' = note->>'id') AS existing
        FROM state),
    saved AS MATERIALIZED (
        SELECT public.charts_runtime('commit', %(project)s, %(board)s || jsonb_build_object(
            'expected', revision, 'at', %(at)s::text, 'previousNotes', notes,
            'document', jsonb_set(doc, '{manifest,annotations}', notes || jsonb_build_array(note)))) AS doc
        FROM merged WHERE existing IS NULL AND jsonb_array_length(notes) < 100
            AND (%(component)s::text IS NULL OR components IS NULL OR components ? %(component)s::text))
    SELECT jsonb_build_object('dashboardId', doc->'id', 'revision', revision,
        'annotation', CASE WHEN existing IS NOT NULL THEN existing
                           WHEN EXISTS (SELECT FROM saved) THEN note END,
        'limitReached', jsonb_array_length(notes) >= 100)
    FROM merged
"""


def cloud_enabled():
    backend = os.environ.get('CHARTS_STORAGE_BACKEND', 'local')
    require(backend in ('local', 'cloudbase', 'cloudflare', 'neon'), 'Unknown CHARTS_STORAGE_BACKEND', 'INVALID_CONFIG')
    return backend in ('cloudbase', 'neon')


@contextmanager
def neon_view_connections():
    if os.environ.get('CHARTS_STORAGE_BACKEND') != 'neon':
        yield
        return
    from psycopg import Connection
    from psycopg_pool import ConnectionPool

    database = CloudDatabase()
    pool: ConnectionPool[Connection] = ConnectionPool(
        database.database_url, connection_class=Connection, min_size=2, max_size=6, timeout=10, open=False,
        kwargs={'connect_timeout': 10, 'prepare_threshold': None, 'autocommit': True})
    with pool:
        token = _VIEW_CONNECTIONS.set(pool)
        try:
            yield
        finally:
            _VIEW_CONNECTIONS.reset(token)


class CloudDatabase:
    def __init__(self):
        self.backend = os.environ.get('CHARTS_DATABASE_BACKEND',
                                      'neon' if os.environ.get('CHARTS_STORAGE_BACKEND') == 'neon' else 'cloudbase')
        require(self.backend in ('cloudbase', 'neon'), 'Unknown CHARTS_DATABASE_BACKEND', 'INVALID_CONFIG')
        if self.backend == 'neon':
            self.database_url = os.environ.get('DATABASE_URL', '')
            require(bool(self.database_url), 'Configure DATABASE_URL', 'INVALID_CONFIG')
            self.url = '/rpc/charts_runtime'
            return
        environment = os.environ.get('CLOUDBASE_ENV_ID', '')
        require(re.fullmatch(r'[a-zA-Z0-9-]+', environment) is not None,
                'Configure CLOUDBASE_ENV_ID', 'INVALID_CONFIG')
        self.key = os.environ.get('CLOUDBASE_API_KEY', '')
        require(bool(self.key), 'Configure the server CloudBase API Key', 'INVALID_CONFIG')
        self.url = f'https://{environment}.api.tcloudbasegateway.com/v1/rdb/rest/rpc/charts_runtime'

    def call(self, action, project='', **payload):
        body = json.dumps({'action': action, 'project': project, 'payload': payload},
                          ensure_ascii=False, allow_nan=False).encode()
        if self.backend == 'neon':
            return self._call_neon(action, project, payload)
        request = Request(self.url, data=body, headers={
            'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=60) as response:
                return json.load(response)
        except HTTPError as error:
            # Never expose gateway bodies, query data, or credential headers.
            raw = error.read()
            codes = {'REVISION_CONFLICT': 409, 'ANNOTATION_CONFLICT': 409,
                     'ALREADY_EXISTS': 409, 'NOT_FOUND': 404,
                     'DATA_CONFLICT': 409, 'DATA_INCOMPLETE': 409,
                     'INVALID_BATCH': 400, 'CHECKPOINT_IN_USE': 409,
                     'PLAN_CHANGED': 409, 'ASSET_UNAVAILABLE': 409,
                     'REVISION_DELETED': 409, 'CONFIRMATION_REQUIRED': 409,
                     'STORAGE_MIGRATED': 409, 'NO_SAVED_VERSION': 404,
                     'FORBIDDEN': 403, 'SHARE_EXPIRED': 410, 'SHARE_UNAVAILABLE': 410,
                     'ANNOTATION_LIMIT': 409}
            try:
                message = json.loads(raw).get('message', '')
            except (ValueError, AttributeError):
                message = ''
            if message in codes:
                label = '暂无已保存版本' if message == 'NO_SAVED_VERSION' else message
                raise DashboardError(message, label, codes[message]) from None
            raise DashboardError('CLOUD_DATABASE_FAILED',
                                 f'PostgreSQL gateway returned HTTP {error.code}', 503) from None
        except (URLError, TimeoutError):
            raise DashboardError('CLOUD_DATABASE_UNAVAILABLE',
                                 'PostgreSQL gateway is unavailable; no local fallback was used', 503) from None

    def _call_neon(self, action, project, payload):
        import psycopg
        from psycopg import sql
        from psycopg.types.json import Jsonb
        from psycopg_pool import PoolTimeout

        function = self.url.rsplit('/', 1)[-1]
        require(function in ('charts_runtime', 'charts_assets', 'charts_release',
                             'charts_delete_checkpoint', 'charts_data_inventory', 'charts_share_annotations'),
                'Unknown PostgreSQL function', 'INVALID_CONFIG')
        pool = _VIEW_CONNECTIONS.get() if function == 'charts_runtime' and action in _POOLED_VIEW_ACTIONS else None
        try:
            checkout = pool.connection() if pool is not None else psycopg.connect(self.database_url, connect_timeout=60)
            with checkout as connection:
                with connection.cursor() as cursor:
                    if function == 'charts_runtime' and action == 'annotation_read':
                        cursor.execute(_ANNOTATION_READ, (project, Jsonb({'board': payload['board']}), payload['includeTargets']))
                    elif function == 'charts_runtime' and action == 'annotation_write':
                        args = {key: payload[key] for key in ('board', 'expected', 'previousNotes', 'at')}
                        cursor.execute(_ANNOTATION_WRITE, (project, Jsonb({'board': payload['board']}), project,
                                                          Jsonb(args), Jsonb(payload['notes'])))
                    elif function == 'charts_runtime' and action == 'annotation_append':
                        # Share the commit lock and take the read snapshot after acquiring it.
                        note = payload['note']
                        with connection.transaction():
                            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended('charts:' || %s, 0))", (project,))
                            cursor.execute(_ANNOTATION_APPEND, {
                                'project': project, 'board': Jsonb({'board': payload['board']}),
                                'note': Jsonb(note), 'at': payload['at'],
                                'component': note.get('componentId') if 'anchor' not in note else None,
                            })
                            row = cursor.fetchone()
                        if row is None:
                            raise DashboardError('CLOUD_DATABASE_FAILED', 'PostgreSQL function returned no row', 503)
                        return row[0]
                    elif function == 'charts_runtime' and action == 'display_revision':
                        cursor.execute("SELECT public.charts_runtime('readable', %s, %s)->'revision'",
                                       (project, Jsonb({'board': payload['board']})))
                    elif function == 'charts_runtime' and action == 'generations_match':
                        cursor.execute("""
                            SELECT NOT EXISTS (
                                SELECT FROM jsonb_each(%s) AS page(board, generation)
                                WHERE page.generation IS DISTINCT FROM public.charts_runtime(
                                    'generation', %s, jsonb_build_object('board', page.board)))
                        """, (Jsonb(payload['pages']), project))
                    else:
                        cursor.execute(
                            sql.SQL('SELECT public.{}(%s, %s, %s)').format(sql.Identifier(function)),
                            (action, project, Jsonb(payload)))
                    row = cursor.fetchone()
                    if row is None:
                        raise DashboardError('CLOUD_DATABASE_FAILED', 'PostgreSQL function returned no row', 503)
                    return row[0]
        except PoolTimeout:
            raise DashboardError('CLOUD_DATABASE_UNAVAILABLE', 'PostgreSQL is busy; please retry', 503) from None
        except psycopg.Error as error:
            codes = {'REVISION_CONFLICT': 409, 'ANNOTATION_CONFLICT': 409,
                     'ALREADY_EXISTS': 409, 'NOT_FOUND': 404,
                     'DATA_CONFLICT': 409, 'DATA_INCOMPLETE': 409,
                     'INVALID_BATCH': 400, 'CHECKPOINT_IN_USE': 409,
                     'PLAN_CHANGED': 409, 'ASSET_UNAVAILABLE': 409,
                     'REVISION_DELETED': 409, 'CONFIRMATION_REQUIRED': 409,
                     'STORAGE_MIGRATED': 409, 'NO_SAVED_VERSION': 404,
                     'FORBIDDEN': 403, 'SHARE_EXPIRED': 410, 'SHARE_UNAVAILABLE': 410,
                     'ANNOTATION_LIMIT': 409}
            message = error.diag.message_primary
            if message in codes:
                label = '暂无已保存版本' if message == 'NO_SAVED_VERSION' else message
                raise DashboardError(message, label, codes[message]) from None
            if isinstance(error, psycopg.OperationalError):
                raise DashboardError('CLOUD_DATABASE_UNAVAILABLE',
                                     'PostgreSQL is unavailable; no local fallback was used', 503) from None
            raise DashboardError('CLOUD_DATABASE_FAILED', 'PostgreSQL request failed', 503) from None
