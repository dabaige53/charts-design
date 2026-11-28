import {test} from 'bun:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtempSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

// @wu-test type=integration | scope=Neon 对象登记与工作区版本 | protects=首次查找返回 SQL NULL 时无法保存新看板或新版本
test('Neon registers new content and reads both saved revisions', () => {
  const {CHARTS_CORE_BIN: binary, CHARTS_TEST_NEON_DATABASE_URL: database} = process.env;
  assert(binary && database, 'Provide the native binary and a dedicated PostgreSQL test database');
  const workspace = mkdtempSync(join(tmpdir(), 'charts-neon-workspace-'));
  const runtime = mkdtempSync(join(tmpdir(), 'charts-neon-runtime-'));
  const args = ['--project-root', workspace, '--runtime-root', runtime, 'call'];
  const env = {...process.env, CHARTS_STORAGE_BACKEND: 'neon', CHARTS_DATABASE_BACKEND: 'neon',
    DATABASE_URL: database, CHARTS_RUNTIME_ROOT: runtime};
  const call = (tool, input) => {
    const result = spawnSync(binary, [...args, tool, '--json-file', '-'], {env, input: JSON.stringify(input),
      encoding: 'utf8', timeout: 30000});
    assert.equal(result.status, 0, result.stderr || result.error?.message);
    return JSON.parse(result.stdout);
  };

  try {
    const dashboardId = 'neon-save';
    const first = call('dashboard_submit', {dashboardId, createTitle: 'First title', operations: [
      {op: 'put_source', id: 'fixture', value: {kind: 'fixture', name: 'Test source'}},
      {op: 'put_dataset', id: 'sales', meta: {sourceId: 'fixture', fields: {amount: {type: 'number'}}},
        rows: [{amount: 12}, {amount: 34}]},
      {op: 'put_component', id: 'details', value: {kind: 'table', title: 'Details', datasetId: 'sales'}},
    ]});
    const second = call('dashboard_submit', {dashboardId, expectedRevision: first.revision, operations: [
      {op: 'set_title', value: 'Second title'},
    ]});
    assert.equal(second.revision, first.revision + 1);
    const previous = call('dashboard_version_get', {dashboardId, revision: first.revision}).version;
    const saved = call('dashboard_preview', {dashboardId}).document;
    assert.equal(previous.manifest.title, 'First title');
    assert.equal(saved.manifest.title, 'Second title');
    assert.equal(saved.snapshot.datasetRefs.sales.version, previous.snapshot.datasetRefs.sales.version);
    assert.equal(call('component_data', {dashboardId, componentId: 'details', expectedRevision: second.revision}).totalRows, 2);
  } finally {
    rmSync(workspace, {recursive: true, force: true});
    rmSync(runtime, {recursive: true, force: true});
  }
}, 60000);
