import { parquetMetadata, parquetRead } from 'hyparquet';

const MAX_PARQUET_BYTES = 24 * 1024 * 1024;
type Rows = Record<string, unknown>[];
export type StaticData = Rows | { rows: Rows; ordinals: number[] };

/** Decode one immutable shard, including its original row order when partitioned. */
export async function decodeParquetData(file: ArrayBuffer): Promise<StaticData> {
  if (file.byteLength > MAX_PARQUET_BYTES) throw Error('Parquet 数据分片超过 24 MiB');
  const metadata = parquetMetadata(file);
  const properties = Object.fromEntries((metadata.key_value_metadata || []).map(item => [item.key, item.value]));
  if (properties['charts.format'] !== 'parquet-v1') throw Error('不支持的 Parquet 数据格式');
  const fields: unknown = JSON.parse(properties['charts.fieldOrder'] || 'null');
  const missingColumn = properties['charts.missingColumn'];
  const ordinalColumn = properties['charts.ordinalColumn'];
  if (!Array.isArray(fields) || !fields.length || !fields.every(field => typeof field === 'string')
      || new Set(fields).size !== fields.length || !missingColumn || fields.includes(missingColumn)) {
    throw Error('Parquet 数据字段不完整');
  }
  if (ordinalColumn !== undefined && (!ordinalColumn || fields.includes(ordinalColumn) || ordinalColumn === missingColumn)) {
    throw Error('Parquet 原始行序字段无效');
  }
  let decoded: unknown[][] = [];
  // Arrays avoid interpreting business field names as JavaScript object properties.
  await parquetRead({ file, metadata, columns: [...fields, missingColumn, ...(ordinalColumn ? [ordinalColumn] : [])], utf8: false,
    onComplete: rows => { decoded = rows; } });
  const ordinals: number[] = [];
  const rows = decoded.map(values => {
    const missing = values[fields.length];
    if (!(missing instanceof Uint8Array) || missing.length !== Math.ceil(fields.length / 8)) {
      throw Error('Parquet 缺失字段标记不完整');
    }
    if (ordinalColumn) {
      const value = values[fields.length + 1];
      const ordinal = typeof value === 'bigint' ? Number(value) : value;
      if (typeof ordinal !== 'number' || !Number.isSafeInteger(ordinal) || ordinal < 1) {
        throw Error('Parquet 原始行序无效');
      }
      ordinals.push(ordinal);
    }
    return Object.fromEntries(fields.flatMap((field, index) => {
      if (missing[index >> 3] & (1 << (index & 7))) return [];
      const value = values[index];
      // Parquet retains int64 exactly. The existing UI, like JSON.parse, computes
      // with JavaScript numbers; do not pass bigint into metrics or filter keys.
      return [[field, typeof value === 'bigint' ? Number(value) : value ?? null]];
    }));
  });
  return ordinalColumn ? { rows, ordinals } : rows;
}

/** Convenience for row-only consumers; the static worker uses the full payload. */
export async function decodeParquet(file: ArrayBuffer): Promise<Rows> {
  const decoded = await decodeParquetData(file);
  return Array.isArray(decoded) ? decoded : decoded.rows;
}

async function boundedParquet(response: Response) {
  if (Number(response.headers.get('content-length')) > MAX_PARQUET_BYTES) {
    await response.body?.cancel().catch(() => {});
    throw Error('Parquet 数据分片超过 24 MiB');
  }
  if (!response.body) throw Error('Parquet 数据分片为空');
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_PARQUET_BYTES) throw Error('Parquet 数据分片超过 24 MiB');
      chunks.push(value);
    }
  } finally { await reader.cancel().catch(() => {}); }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return bytes.buffer;
}

export async function readStaticData(response: Response, pathname: string) {
  if (!response.ok) throw Error(`数据加载失败 (${response.status})`);
  if (pathname.endsWith('.parquet')) {
    return decodeParquetData(await boundedParquet(response));
  }
  return pathname.endsWith('.gz')
    ? new Response(response.body!.pipeThrough(new DecompressionStream('gzip'))).json()
    : response.json();
}
