import { afterEach, test } from 'bun:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { decodeParquet, readStaticData } from './static-data';
import { createStaticQuery } from '../../runtime-ui/shared/static-query.mjs';

const native = process.env.CHARTS_CORE_BIN;
const nativeTest = native ? test : test.skip;
const directories: string[] = [];
afterEach(() => { for (const directory of directories.splice(0)) rmSync(directory, { recursive: true, force: true }); });

function fixture(extraArgs: string[] = []) {
  const directory = mkdtempSync(path.join(tmpdir(), 'charts-parquet-'));
  directories.push(directory);
  const fields = { month: { type: 'date' }, group: { type: 'string' }, n: { type: 'number' },
    d: { type: 'number' }, optional: { type: 'string' }, active: { type: 'boolean' },
    __charts_missing: { type: 'string' }, 整数: { type: 'number' } };
  const rows = [
    { month: '2026-01-01', group: '甲', n: 1, d: 2, optional: null, active: false, __charts_missing: '原始字段', 整数: 0 },
    { month: '2026-01-02', group: '甲', n: 2, d: 8, active: true, __charts_missing: '', 整数: -9 },
    { month: '2026-02-01', group: '乙', n: 3.5, d: 0, optional: '', active: null, 整数: 42 },
  ];
  const call = (tool: string, input: string) => JSON.parse(execFileSync(native!, [
    '--project-root', path.join(directory, 'project'), '--runtime-root', path.join(directory, 'runtime'),
    'call', tool, '--json-file', '-'], { input, encoding: 'utf8' }));
  call('dashboard_create', JSON.stringify({ dashboardId: 'fixture', title: 'Parquet scalar fixture' }));
  // Send the full 64-bit literal to Rust before JavaScript rounds it for display.
  const input = JSON.stringify({ dashboardId: 'fixture', datasetId: 'data', expectedRevision: 1, fields, rows })
    .replace('"整数":0', '"整数":9007199254740993');
  const imported = call('dataset_import', input);
  const reference = imported.document.snapshot.datasetRefs.data;
  const receipt = JSON.parse(execFileSync(native!, ['export-parquet', '--database', path.join(directory, 'project/data/data.sqlite3'),
    '--version', reference.version, '--output', path.join(directory, 'parquet'), ...extraArgs], { encoding: 'utf8' }));
  return { directory, fields, rows: JSON.parse(input).rows, receipt };
}

async function readFileRows(f: ReturnType<typeof fixture>) {
  const parts = await Promise.all(f.receipt.files.map(async (file: { path: string }) => {
    const buffer = readFileSync(path.join(f.directory, 'parquet', file.path));
    return decodeParquet(buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength));
  }));
  return parts.flat();
}

// @wu-test type=integration | scope=Rust→Parquet→网页Worker | protects=缺失键被改成null或日期布尔整数及字段名被转坏
nativeTest('native Parquet preserves the existing web scalar and missing-key contract', async () => {
  const f = fixture();
  const restored = await readFileRows(f);
  assert.deepEqual(restored, f.rows);
  assert.equal('optional' in restored[1], false);
  assert.equal(restored[0].optional, null);
  assert.equal(restored[0].__charts_missing, '原始字段');
});

// @wu-test type=integration | scope=Parquet静态查询语义 | protects=格式切换改变筛选比率分组搜索分页或CSV结果
nativeTest('Parquet and JSON feed identical filters, ratios, details and CSV exports', async () => {
  const f = fixture();
  const doc = { id: 'fixture', revision: 1, manifest: { filters: [], datasets: { sales: { fields: f.fields } },
    metrics: { ratio: { aggregation: 'ratio', numerator: 'n', denominator: 'd', scale: 100 } },
    components: { card: { kind: 'legacy', family: 'kpi', datasetId: 'sales', binding: { measures: { value: 'ratio' } }, config: { type: 'mc01' } },
      table: { kind: 'table', datasetId: 'sales', config: {}, presentation: { columns: [
        { key: 'group', title: '分组' }, { key: 'n', title: '分子' }, { key: 'd', title: '分母' } ], groupBy: ['group'], sumFields: ['n', 'd'] } } } },
    snapshot: { datasets: {} }, staticFiles: { sales: ['fixture'] } };
  const legacy = createStaticQuery(doc, async () => f.rows);
  const columnar = createStaticQuery(doc, async () => readFileRows(f));
  const filters = [{ field: 'group', op: 'in', values: ['甲'], componentIds: ['card', 'table'] }];
  const queries = [
    { componentIds: ['card', 'table'], filters },
    { componentIds: ['table'], tableStates: { table: { pageSize: 1, sortCol: 'n', sortDir: 'desc' } } },
    { componentIds: ['table'], export: {}, filters },
    { detail: true, componentId: 'card', search: 'null', limit: 10 },
    { detail: true, componentId: 'card', filters: [{ field: 'optional', op: 'in', values: [null], componentIds: ['card'] }] },
  ];
  for (const query of queries) assert.deepEqual(await columnar.query(query), await legacy.query(query));
  assert.equal((await columnar.query(queries[4])).totalRows, 1);
});

// @wu-test type=integration | scope=云端Parquet分区和候选项 | protects=分区改变原始行序或筛选下载全部行或候选项仍依赖JSON
nativeTest('native partition ordinals and columnar options feed the real static query', async () => {
  const f = fixture(['--partition-field', 'group', '--include-options']);
  const doc = { id: 'partitioned', revision: 1, manifest: { datasets: { data: { fields: f.fields } },
    filters: [{ id: 'optional', field: 'optional', op: 'in', values: [], componentIds: ['rows'] }],
    components: { rows: { kind: 'table', datasetId: 'data', config: {} } } }, snapshot: { datasets: {} },
    staticFiles: { data: f.receipt.files.map((file: { path: string }) => file.path) },
    staticPartitionIndexes: { data: f.receipt.partitionIndex }, staticOptions: { data: {
      optional: { field: 'optional', files: f.receipt.options.optional.map((file: { path: string }) => file.path) },
    } } };
  const calls: string[] = [];
  const load = async (name: string) => {
    calls.push(name);
    return readStaticData(new Response(new Uint8Array(readFileSync(path.join(f.directory, 'parquet', name)))), name);
  };
  const query = createStaticQuery(doc, load);
  assert.deepEqual((await query.query({ filterId: 'optional' })).values, [null, '']);
  assert.deepEqual(calls, doc.staticOptions.data.optional.files);
  calls.length = 0;
  const filters = [{ field: 'group', op: 'in', values: ['甲'], componentIds: ['rows'] }];
  assert.deepEqual((await query.query({ detail: true, componentId: 'rows', filters })).rows, f.rows.slice(0, 2));
  assert.deepEqual(calls, f.receipt.partitionIndex.entries.find((entry: { value: string }) => entry.value === '甲').files);
  assert.deepEqual((await query.query({ detail: true, componentId: 'rows', filters: [] })).rows, f.rows);
});

// @wu-test type=boundary | scope=Parquet格式验证 | protects=损坏或超限分片被当成成功的空数据
test('invalid Parquet and oversized shards fail explicitly', async () => {
  await assert.rejects(decodeParquet(new ArrayBuffer(0)));
  await assert.rejects(decodeParquet(new ArrayBuffer(24 * 1024 * 1024 + 1)), /24 MiB/);
});

// @wu-test type=boundary | scope=Parquet流式读取边界 | protects=没有Content-Length时超限响应仍持续分配内存
test('a streamed Parquet response is cancelled as soon as it crosses its limit', async () => {
  let cancelled = false;
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new Uint8Array(16 * 1024 * 1024));
      controller.enqueue(new Uint8Array(9 * 1024 * 1024));
    },
    cancel() { cancelled = true; },
  });
  await assert.rejects(readStaticData(new Response(stream), 'data.parquet'), /24 MiB/);
  assert.equal(cancelled, true);
  cancelled = false;
  const declared = new Response(new ReadableStream({ cancel() { cancelled = true; } }), {
    headers: { 'Content-Length': String(25 * 1024 * 1024) },
  });
  await assert.rejects(readStaticData(declared, 'data.parquet'), /24 MiB/);
  assert.equal(cancelled, true);
});
