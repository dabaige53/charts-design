"""Targeted real PostgreSQL transaction checks; CI supplies an isolated database."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import uuid

import pytest

URL = os.environ.get('CHARTS_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires isolated PostgreSQL test database')


def sql(source):
    result = subprocess.run(['psql', URL, '-XAt', '-v', 'ON_ERROR_STOP=1'],
                            input=source, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


@pytest.fixture(scope='module')
def database():
    sql("""
        CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
        CREATE SCHEMA auth;
        CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql AS
        'SELECT coalesce(current_setting(''request.jwt.claims'',true),''{}'')::jsonb->>''role''';
    """)
    for migration in sorted(Path('cloudbase/migrations').glob('*.sql')):
        sql(migration.read_text())
    return 'annotation-ci-' + uuid.uuid4().hex[:12]


def rpc(project, command, revision=1, role='service_role'):
    payload = json.dumps({'board': 'board', 'revision': revision, 'command': command, 'at': '2026-11-12'}).replace("'", "''")
    raw = sql(f"""SET request.jwt.claims='{{"role":"{role}"}}';
        SELECT public.charts_annotation('apply','{project}','{payload}'::jsonb);""")
    return json.loads(raw.splitlines()[-1])


def cmd(action, annotation, **kwargs):
    return {'operationId': uuid.uuid4().hex, 'action': action, 'annotationId': annotation, **kwargs}


# @wu-test type=integration | scope=charts_annotation PostgreSQL transactions | protects=五个独立数据库会话新增回复及修改不同批注互相覆盖或网络重试重复保存
def test_five_postgres_sessions(database):
    project = database
    sql(f"""INSERT INTO charts.projects VALUES('{project}','{{}}');
        INSERT INTO charts.boards(project,id,document) VALUES('{project}','board',
        '{{"id":"board","revision":1,"manifest":{{"title":"Retained"}},"snapshot":{{}}}}');""")
    adds = [cmd('add', f'n{i}', value={'text': f'Note {i}', 'createdAt': 'today'}) for i in range(5)]
    with ThreadPoolExecutor(5) as pool:
        list(pool.map(lambda c: rpc(project, c), adds))
        replies = [cmd('reply', 'n0', value={'id': f'r{i}', 'text': f'Reply {i}', 'createdAt': 'today'}) for i in range(5)]
        list(pool.map(lambda c: rpc(project, c), replies))
        edits = [cmd('edit', f'n{i}', expectedVersion=1, value={'text': f'Changed {i}'}) for i in range(5)]
        list(pool.map(lambda c: rpc(project, c), edits))
    rpc(project, adds[0])
    rpc(project, replies[0])
    notes = json.loads(sql(f"SELECT notes FROM charts.boards WHERE project='{project}' AND id='board';"))
    assert len(notes) == 5
    assert {n['text'] for n in notes} == {f'Changed {i}' for i in range(5)}
    assert len(next(n for n in notes if n['id'] == 'n0')['replies']) == 5
    assert sql(f"SELECT document->>'revision' FROM charts.boards WHERE project='{project}' AND id='board';") == '1'
    with pytest.raises(RuntimeError, match='ANNOTATION_CONFLICT'):
        rpc(project, cmd('edit', 'n0', expectedVersion=1, value={'text': 'Stale'}))
    with pytest.raises(RuntimeError, match='FORBIDDEN'):
        rpc(project, adds[0], role='anon')
    with pytest.raises(RuntimeError, match='REVISION_CONFLICT'):
        rpc(project, cmd('delete', 'n0', expectedVersion=2), revision=99)
    rpc(project, cmd('delete', 'n0', expectedVersion=2))
    rpc(project, adds[0])
    with pytest.raises(RuntimeError, match='ANNOTATION_NOT_FOUND'):
        rpc(project, cmd('reply', 'n0', value={'id': 'late', 'text': 'Late', 'createdAt': 'today'}))
    assert json.loads(sql(f"SELECT jsonb_array_length(notes) FROM charts.boards WHERE project='{project}' AND id='board';")) == 4
