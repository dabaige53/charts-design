"""Publication feedback boundaries: real files, versioned exports and HTTP sessions."""
from concurrent.futures import ThreadPoolExecutor
import io
import json
import re
import shutil
import subprocess
import time
import zipfile

import pytest

from dashboard_runtime.cloud_shares import CloudShares, cleanup_due
from dashboard_runtime.cloudflare_shares import PrivateShares
from dashboard_runtime.demo import executive_document, report_document
from dashboard_runtime.deployment import export_site
from dashboard_runtime.model import DashboardError
from dashboard_runtime.service import Service
from dashboard_runtime.share_annotations import LocalShareAnnotations


def publication(tmp_path, *, mode='annotate', pages=False):
    author = Service(tmp_path / 'author-runtime', project_root=tmp_path / 'author')
    for board, factory in [('board', executive_document), ('report', report_document)]:
        author.store.create(board, board, factory(board))
        author.call('dashboard_version_publish', {'dashboardId': board, 'expectedRevision': 1, 'revision': 1})
    store = PrivateShares(tmp_path / 'cloud')
    store.put('cleaner-status.json', json.dumps({'completedAt': int(time.time())}).encode())
    shares = CloudShares(store, 'https://charts.example')
    result = shares.publish(author, 'board', 1, access_key='01234567', annotation_mode=mode,
                            pages=[{'dashboardId': 'report', 'expectedRevision': 1}] if pages else None)
    return author, store, shares, result


def note(note_id='note-a', component=None, quote='报告段落'):
    return {'id': note_id, 'componentId': component, 'text': '请核对这项结果', 'createdAt': '2026-11-27T01:00:00Z',
            'anchor': {'scope': 'component' if component else 'text', 'kind': 'element', 'quote': quote,
                       'occurrence': 0, 'rect': {'x': .1, 'y': .1, 'width': .2, 'height': .2}},
            'view': {'revision': 1, 'filters': []}}


def entry_action(html, fragment):
    script = re.search(r'<script id="charts-share-entry">([\s\S]*?)</script>', html).group(1)
    program = """
        import vm from 'node:vm';
        let input=''; for await (const part of process.stdin) input+=part;
        const {script,fragment}=JSON.parse(input);
        const location=new URL('https://charts.example/s/'+'a'.repeat(32)+'/'+fragment);
        const posts=[],nodes=[];
        const document={body:{appendChild(node){nodes.push(node);}},createElement(tag){
            return {tag,appendChild(input){this.input=input;},submit(){posts.push({field:this.input.name,value:this.input.value});}};
        }};
        const history={replaceState(_state,_title,url){location.href=new URL(url,location).href;}};
        vm.runInNewContext(script,{document,location,history,URLSearchParams});
        console.log(JSON.stringify({posts,hash:location.hash,app:nodes.some(node=>node.tag==='script'&&node.src==='app.js')}));
    """
    result = subprocess.run(['node', '--input-type=module', '-e', program],
                            input=json.dumps({'script': script, 'fragment': fragment}), text=True,
                            capture_output=True, check=True, timeout=10)
    return json.loads(result.stdout)


# @wu-test type=integration | scope=publication annotations and fixed versions | protects=读者批注跟随草稿、泄露作者私有批注、跨分享污染或重新生成数据和内容版本
def test_share_feedback_is_independent_and_pinned_for_components_and_report(tmp_path, monkeypatch):
    monkeypatch.setenv('CHARTS_STORAGE_BACKEND', 'local')
    author, storage, shares, receipt = publication(tmp_path, pages=True)
    share_id = receipt['shareId']
    document = json.loads(shares.content(share_id, 'document.json'))
    component = next(iter(document['manifest']['components']))
    author.store.append_annotation('board', note('private-note', component))
    other = shares.publish(author, 'board', 1, annotation_mode='annotate')
    assert not json.loads(shares.content(other['shareId'], 'document.json'))['manifest'].get('annotations')
    before = {name: shares.content(share_id, name) for name in shares.control(share_id)['files']}
    version_before = author.call('dashboard_version_status', {'dashboardId': 'board'})
    saved = shares.append_annotation(share_id, 'board', note(component=component), '读者')
    assert saved['annotation']['author'] == {'name': '读者', 'verified': False}
    assert saved['annotation']['context']['shareId'] == share_id
    assert shares.append_annotation(share_id, 'board', note(component=component), '读者') == saved
    with pytest.raises(DashboardError, match='编号'):
        shares.append_annotation(share_id, 'board', {**note(component=component), 'text': 'different'}, '读者')
    report_note = shares.append_annotation(share_id, 'report', note('report-note'))
    assert report_note['annotation']['context']['designRevision'] == 1
    assert shares.annotations(other['shareId'], 'board')['annotations'] == []
    assert author.call('dashboard_version_status', {'dashboardId': 'board'}) == version_before
    assert {name: shares.content(share_id, name) for name in before} == before
    assert [item['id'] for item in author.store.annotation_state('board')['annotations']] == ['private-note']
    author.store.mutate('board', 1, [{'op': 'set_title', 'value': 'B'}, {'op': 'remove_component', 'id': component}])
    author.store.checkpoint('board', 2)
    reopened = CloudShares(PrivateShares(tmp_path / 'cloud'), 'https://charts.example')
    assert reopened.annotations(share_id, 'board')['revision'] == 1
    assert component in json.loads(reopened.content(share_id, 'document.json'))['manifest']['components']
    assert reopened.annotations(share_id, 'board')['annotations'][0]['componentId'] == component
    assert reopened.annotations(share_id, 'report')['annotations'][0]['anchor']['quote'] == '报告段落'


# @wu-test type=boundary | scope=share annotation persistence concurrency | protects=并发新增互相覆盖、同ID重试重复写入或撤销后仍可写入
def test_annotation_storage_merges_parallel_appends_and_rejects_revoked_scope(tmp_path):
    store = LocalShareAnnotations(tmp_path)
    share_id = 'a' * 32
    store.call('configure', shareId=share_id, owner='owner', pages=[{'id': 'board', 'revision': 1}],
               expiresAt=None, annotationMode='annotate')
    store.call('activate', shareId=share_id)

    def append(index):
        item = note('note-' + str(index))
        item['context'] = {'shareId': share_id, 'designRevision': 1}
        return store.call('append', shareId=share_id, dashboardId='board', annotation=item, fingerprint=str(index))

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert len(list(pool.map(append, [*range(12), *range(12)]))) == 24
    assert len(store.call('read', shareId=share_id, dashboardId='board')) == 12
    store.call('revoke', shareId=share_id)
    with pytest.raises(DashboardError) as error:
        append(20)
    assert error.value.code == 'SHARE_EXPIRED'


# @wu-test type=integration | scope=publication reader and feedback HTTP permissions | protects=越权写批注或内容、失效分享继续读写、反馈权限升级与回执丢失后重复新增
def test_reader_http_enforces_scope_permission_expiry_and_feedback(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    from dashboard_runtime.server import RemoteServer, ServerSettings, create_app
    monkeypatch.setenv('CHARTS_STORAGE_BACKEND', 'local')
    author, storage, shares, receipt = publication(tmp_path)
    readonly = shares.publish(author, 'board', 1, access_key='98765432')
    settings = ServerSettings(workspace=tmp_path / 'server', runtime=tmp_path / 'server-runtime',
                              public_url='https://charts.example', tokens=('server-secret-token-test',))
    server = RemoteServer(settings)
    server.cloud_shares = shares
    sid, rid = receipt['shareId'], readonly['shareId']
    root = '/s/' + sid + '/'
    endpoint = root + 'api/annotations'
    with TestClient(create_app(server), base_url='https://charts.example') as client:
        assert client.get(endpoint).status_code == 401
        assert client.post(root, data={'accessKey': '01234567'}, follow_redirects=False).status_code == 303
        entry = client.get(root)
        assert entry.headers['referrer-policy'] == 'same-origin'
        assert entry_action(entry.text, '#feedback=example-token') == {
            'posts': [{'field': 'feedbackToken', 'value': 'example-token'}], 'hash': '', 'app': False}
        assert entry_action(entry.text, '') == {'posts': [], 'hash': '', 'app': True}
        response = client.post(endpoint, json={'dashboardId': 'board', 'revision': 1, 'append': note()})
        assert response.status_code == 200, response.text
        assert client.get(endpoint, params={'dashboardId': 'board'}).json()['count'] == 1
        assert client.get(endpoint, params={'dashboardId': 'board', 'revision': 2}).status_code == 409
        assert client.post(endpoint, json={'dashboardId': 'board', 'revision': 2, 'append': note('wrong-version')}).status_code == 409
        original_call, failed = LocalShareAnnotations.call, []

        def committed_then_lost(database, action, project='', **payload):
            result = original_call(database, action, project, **payload)
            if action == 'append' and not failed:
                failed.append(True)
                raise OSError('simulated response failure after commit')
            return result

        with monkeypatch.context() as patch:
            patch.setattr(LocalShareAnnotations, 'call', committed_then_lost)
            body = {'dashboardId': 'board', 'revision': 1, 'append': note('retry-note')}
            assert client.post(endpoint, json=body).status_code == 500
            assert client.post(endpoint, json=body).status_code == 200
            notes = client.get(endpoint).json()['annotations']
            assert sum(item['id'] == 'retry-note' for item in notes) == 1
        assert client.get(endpoint, params={'dashboardId': 'other'}).status_code == 403
        assert client.post(endpoint, json={'append': note('csrf')}, headers={'Origin': 'https://attacker.example'}).status_code == 403
        assert client.get('/s/' + rid + '/api/annotations').status_code == 401
        assert client.post('/s/' + rid + '/', data={'accessKey': '98765432'}, follow_redirects=False).status_code == 303
        assert client.post('/s/' + rid + '/api/annotations', json={'append': note()}).status_code == 403
        assert client.post('/api/v1/p/default/tools/dashboard_patch', json={'dashboardId': 'board', 'operations': []}).status_code == 401
        feedback = server.signer.sign({'k': 'share-feedback', 'shareId': sid, 'exp': int(time.time()) + 60})
        assert client.post(root, data={'feedbackToken': feedback}, follow_redirects=False).status_code == 303
        assert client.get(endpoint).json()['canAnnotate'] is False
        assert client.get(root + 'document.json').json()['annotationAccess']['canAnnotate'] is False
        assert client.post(endpoint, json={'append': note('forbidden')}).status_code == 403
        assert entry_action(client.get(root).text, '#key=01234567') == {
            'posts': [{'field': 'accessKey', 'value': '01234567'}], 'hash': '', 'app': False}
        assert client.post(root, data={'accessKey': '01234567'}, follow_redirects=False).status_code == 303
        assert client.get(root + 'document.json').json()['annotationAccess']['canAnnotate'] is True
        shares.revoke(author, 'board', sid)
        assert client.get(endpoint).status_code == 410
        assert client.post(endpoint, json={'append': note('revoked')}).status_code == 410
        control = shares.control(rid)
        shares._put_json('shares/' + rid + '/control.json', {**control, 'expiresAt': time.time() - 1})
        assert client.get('/s/' + rid + '/api/annotations').status_code == 410


# @wu-test type=integration | scope=local frozen ZIP import and independent service | protects=分享依赖作者磁盘在线、重试重复发布、ZIP路径穿越或仅上传页面遗漏查询数据
def test_imported_share_survives_author_removal_and_retry(tmp_path, monkeypatch):
    monkeypatch.setenv('CHARTS_STORAGE_BACKEND', 'local')
    author, storage, shares, _ = publication(tmp_path, mode='view')
    exported = export_site(author.store, 'board', data_format='json')['export']
    raw = open(exported['path'], 'rb').read()
    args = {'source_key': 'b' * 64, 'request_id': 'request-1', 'secret': b's' * 32, 'annotation_mode': 'annotate'}
    result = shares.import_site(io.BytesIO(raw), **args)
    assert shares.import_site(io.BytesIO(raw), **args) == result
    with pytest.raises(DashboardError) as error:
        shares.import_site(io.BytesIO(raw), **{**args, 'annotation_mode': 'view'})
    assert error.value.code == 'REVISION_CONFLICT'
    with pytest.raises(DashboardError):
        shares.owner_control(result['shareId'], 'c' * 64)
    shutil.rmtree(author.project_root)
    shutil.rmtree(tmp_path / 'author-runtime')
    restarted = CloudShares(PrivateShares(tmp_path / 'cloud'), 'https://charts.example')
    document = json.loads(restarted.content(result['shareId'], 'document.json'))
    assert document['revision'] == 1
    assert restarted.content(result['shareId'], next(iter(document['staticFiles'].values()))[0])
    restarted.append_annotation(result['shareId'], 'board', note())
    assert restarted.annotations(result['shareId'], 'board')['count'] == 1
    restarted.revoke_owner(result['shareId'], 'b' * 64)
    cleanup_due(storage, now=time.time() + 1)
    assert not list(storage.list('shares/' + result['shareId'] + '/'))
    malicious = io.BytesIO()
    with zipfile.ZipFile(malicious, 'w') as package:
        package.writestr('../control.json', '{}')
    with pytest.raises(DashboardError, match='path'):
        shares.import_site(malicious, **{**args, 'request_id': 'request-2'})


# @wu-test type=boundary | scope=retired publication identities | protects=到期或撤销清理后同 requestId 复活原分享 ID 和访问密钥
@pytest.mark.parametrize('mode', ['view', 'annotate'])
@pytest.mark.parametrize('retirement', ['revoke', 'expire'])
def test_cleaned_publication_request_never_reactivates(tmp_path, monkeypatch, mode, retirement):
    monkeypatch.setenv('CHARTS_STORAGE_BACKEND', 'local')
    author, storage, shares, _ = publication(tmp_path, mode='view')
    exported = export_site(author.store, 'board', data_format='json')['export']
    raw = open(exported['path'], 'rb').read()
    args = {'source_key': 'd' * 64, 'request_id': 'retired-request', 'secret': b's' * 32,
            'annotation_mode': mode, 'expiration': '7d'}
    result = shares.import_site(io.BytesIO(raw), **args)
    share_id = result['shareId']
    if retirement == 'revoke':
        shares.revoke_owner(share_id, args['source_key'])
        now = time.time() + 1
    else:
        now = result['expiresAt'] + 1
    assert not cleanup_due(storage, now=now)['failed']
    assert storage.get('retired/' + share_id) == b''
    assert not list(storage.list('shares/' + share_id + '/'))
    assert storage.get('jobs/' + share_id + '.json') is None
    restarted = CloudShares(PrivateShares(tmp_path / 'cloud'), 'https://charts.example')
    for action in (lambda: restarted.import_site(io.BytesIO(raw), **args),
                   lambda: restarted.quick_result(share_id, result['accessKey'], '7d'),
                   lambda: restarted.authenticate(share_id, result['accessKey'])):
        with pytest.raises(DashboardError) as error:
            action()
        assert error.value.code == 'SHARE_EXPIRED'
    assert not cleanup_due(storage, now=now)['failed']
    assert storage.get('retired/' + share_id) == b''


# @wu-test type=boundary | scope=publication claim crash recovery | protects=配置原子占位后崩溃留下永久孤儿或过期 intent 错删已经激活的分享
@pytest.mark.parametrize('crash', ['before_job', 'before_activation', 'after_activation'])
def test_publication_claim_crash_is_cleanable_without_retiring_active_copy(tmp_path, monkeypatch, crash):
    monkeypatch.setenv('CHARTS_STORAGE_BACKEND', 'local')
    author, storage, shares, _ = publication(tmp_path, mode='view')
    exported = export_site(author.store, 'board', data_format='json')['export']
    raw = open(exported['path'], 'rb').read()
    args = {'source_key': 'e' * 64, 'request_id': 'crash-request', 'secret': b's' * 32,
            'annotation_mode': 'annotate', 'expiration': 'never'}
    original_call, original_delete = LocalShareAnnotations.call, storage.delete_prefix
    interrupted_job = {}

    def fail_stage(_share_id, job):
        interrupted_job.update(job)
        raise OSError('simulated crash before job')

    def fail_activate(database, action, project='', **payload):
        if action == 'activate':
            raise OSError('simulated crash before scope activation')
        return original_call(database, action, project, **payload)

    def fail_intent_delete(prefix):
        if prefix.startswith('publication-intents/'):
            raise OSError('simulated crash after scope activation')
        return original_delete(prefix)

    with monkeypatch.context() as patch:
        if crash == 'before_job':
            patch.setattr(shares, '_stage', fail_stage)
        elif crash == 'before_activation':
            patch.setattr(LocalShareAnnotations, 'call', fail_activate)
        else:
            patch.setattr(storage, 'delete_prefix', fail_intent_delete)
        with pytest.raises(OSError, match='simulated crash'):
            shares.import_site(io.BytesIO(raw), **args)
    [intent_key] = list(storage.list('publication-intents/'))
    intent = json.loads(storage.get(intent_key))
    share_id = intent['shareId']
    if crash == 'before_job':
        with monkeypatch.context() as patch:
            patch.setattr(time, 'time', lambda: intent['cleanupAfter'] + 1)
            with pytest.raises(DashboardError) as error:
                shares.import_site(io.BytesIO(raw), **args)
            assert error.value.code == 'SHARE_EXPIRED'
        assert json.loads(storage.get(intent_key)) == intent
    if crash == 'before_activation':
        # A changed request must not replace the legitimate, incomplete claim.
        with pytest.raises(DashboardError) as error:
            shares.import_site(io.BytesIO(raw), **{**args, 'annotation_mode': 'view'})
        assert error.value.code == 'REVISION_CONFLICT'
        result = shares.import_site(io.BytesIO(raw), **args)
        assert result['shareId'] == share_id
        assert shares.append_annotation(share_id, 'board', note('retry-activation'))['annotation']['id'] == 'retry-activation'
    outcome = cleanup_due(storage, now=intent['cleanupAfter'] + 1)
    assert not outcome['failed']
    assert storage.get(intent_key) is None
    if crash in ('before_activation', 'after_activation'):
        assert storage.get('retired/' + share_id) is None
        result = shares.import_site(io.BytesIO(raw), **args)
        assert result['shareId'] == share_id
        assert shares.append_annotation(share_id, 'board', note())['annotation']['id'] == 'note-a'
    else:
        assert storage.get('retired/' + share_id) == b''
        assert not list(storage.list('shares/' + share_id + '/'))
        with pytest.raises(DashboardError) as error:
            shares.import_site(io.BytesIO(raw), **args)
        assert error.value.code == 'SHARE_EXPIRED'
        # A killed upload may never reach activation or recreate a job.
        storage.put('shares/' + share_id + '/site/abandoned.json', b'{"late":true}')
        assert storage.get('jobs/' + share_id + '.json') is None
        assert not cleanup_due(storage, now=intent['cleanupAfter'] + 1)['failed']
        assert not list(storage.list('shares/' + share_id + '/'))
        # An upload that was already in flight can finish writing after cleanup.
        # Even the first activation guard must recreate its removal task.
        storage.put('shares/' + share_id + '/site/late.json', b'{"late":true}')
        with pytest.raises(DashboardError) as error:
            shares._activate({**interrupted_job, 'state': 'active'},
                             {**interrupted_job, 'state': 'active', 'cleanupAfter': None})
        assert error.value.code == 'SHARE_EXPIRED'
        assert json.loads(storage.get('jobs/' + share_id + '.json'))['state'] == 'revoked'
        assert not cleanup_due(storage, now=intent['cleanupAfter'] + 1)['failed']
        assert not list(storage.list('shares/' + share_id + '/'))
