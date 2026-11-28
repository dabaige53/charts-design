export const CHUNK_SIZE = 1024 * 1024;
export const MAX_ARCHIVE = 16 * CHUNK_SIZE;
const MAX_DOCUMENT = CHUNK_SIZE;
const decoder = new TextDecoder("utf-8", { fatal: true });

export class ShareError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function check(condition, status, code, message) {
  if (!condition) throw new ShareError(status, code, message);
}

const validZip = condition => check(condition, 400, "INVALID_ARCHIVE", "Invalid publication ZIP");

export async function boundedBody(request, limit) {
  check(Number(request.headers.get("content-length")) <= limit && request.body,
    413, "PAYLOAD_TOO_LARGE", "The request exceeds the size limit");
  const reader = request.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length;
      check(size <= limit, 413, "PAYLOAD_TOO_LARGE", "The request exceeds the size limit");
      chunks.push(value);
    }
  } finally {
    await reader.cancel();
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.length;
  }
  return body;
}

export function inflated(stream, method) {
  return method === 8 ? stream.pipeThrough(new DecompressionStream("deflate-raw")) : stream;
}

export function entries(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.length);
  const read16 = offset => view.getUint16(offset, true);
  const read32 = offset => view.getUint32(offset, true);
  const end = bytes.length - 22;
  validZip(end >= 0 && read32(end) === 0x06054b50 && read32(end + 4) === 0 && read16(end + 20) === 0);
  const total = read16(end + 10);
  validZip(total === read16(end + 8) && total <= 4096);
  let offset = read32(end + 16);
  const central = offset;
  validZip(read32(end + 12) + central === end);
  const result = new Map();
  for (let entry = 0; entry < total; entry++) {
    validZip(offset + 46 <= end && read32(offset) === 0x02014b50);
    const flags = read16(offset + 8), method = read16(offset + 10);
    const compressed = read32(offset + 20), size = read32(offset + 24);
    const nameSize = read16(offset + 28), extraSize = read16(offset + 30), commentSize = read16(offset + 32);
    const local = read32(offset + 42);
    validZip((flags & ~0x808) === 0 && (method === 0 || method === 8) && offset + 46 + nameSize + extraSize + commentSize <= end);
    const name = decoder.decode(bytes.subarray(offset + 46, offset + 46 + nameSize));
    validZip(!result.has(name) && local + 30 <= central && read32(local) === 0x04034b50 &&
      read16(local + 8) === method && read16(local + 26) === nameSize);
    const start = local + 30 + nameSize + read16(local + 28);
    validZip(start + compressed <= central && (method !== 0 || size === compressed) &&
      decoder.decode(bytes.subarray(local + 30, local + 30 + nameSize)) === name);
    result.set(name, { start, compressed, size, method });
    offset += 46 + nameSize + extraSize + commentSize;
  }
  validZip(offset === end);
  return result;
}

export async function entryBytes(bytes, entry) {
  const input = bytes.subarray(entry.start, entry.start + entry.compressed);
  const body = inflated(new Blob([input]).stream(), entry.method);
  const raw = await boundedBody(new Request("https://archive.invalid/", { method: "POST", body, duplex: "half" }), entry.size);
  validZip(raw.length === entry.size);
  return raw;
}

async function jsonEntry(bytes, entry) {
  validZip(entry && entry.size <= MAX_DOCUMENT);
  return JSON.parse(decoder.decode(await entryBytes(bytes, entry)));
}

export async function publicationBundle(bytes, { pages = false } = {}) {
  try {
    const all = entries(bytes);
    const document = await jsonEntry(bytes, all.get("document.json"));
    const manifest = await jsonEntry(bytes, all.get("export-manifest.json"));
    const id = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/;
    validZip(document?.schemaVersion === 2 && typeof document.id === "string" && id.test(document.id) && Number.isSafeInteger(document.revision) &&
      document.revision >= 1 && manifest?.dashboardId === document.id && manifest.revision === document.revision &&
      typeof document.manifest?.title === "string" && document.manifest?.components && document.staticFiles && !document.staticPages &&
      !document.staticOptions && !document.staticPartitionIndexes);
    const names = new Set();
    for (const group of Object.values(document.staticFiles)) {
      validZip(Array.isArray(group));
      if (pages) check(group.length === 1 && typeof group[0] === "string" && group[0].endsWith(".parquet"),
        422, "SINGLE_PARQUET_REQUIRED", "Export one Parquet per dataset for Pages snapshots");
      for (const path of group) {
        validZip(typeof path === "string" && /^data\/[a-zA-Z0-9_-]+\.(parquet|json\.gz)$/.test(path) && all.has(path));
        names.add(path);
      }
    }
    for (const key of ["sources", "queries", "annotations"]) delete document.manifest[key];
    for (const key of ["browserLinks", "annotationAccess", "publicationApiBase", "publication", "annotationsOpen"]) delete document[key];
    document.snapshot = { datasets: {} };

    if (pages) {
      const size = Array.from(names, path => all.get(path).size).reduce((total, bytes) => total + bytes, 0);
      check(size <= 24 * CHUNK_SIZE, 413, "PAYLOAD_TOO_LARGE", "A Pages snapshot can contain up to 24 MiB of Parquet data");
      return { document, async *assets() {
        for (const path of names) yield [path, await entryBytes(bytes, all.get(path))];
      } };
    }

    const files = {};
    let length = 0;
    for (const path of names) {
      const entry = all.get(path);
      validZip(entry.size <= 24 * CHUNK_SIZE);
      files[path] = { ...entry, packed: length };
      length += entry.compressed;
    }
    const packed = new Uint8Array(length);
    for (const entry of Object.values(files)) {
      packed.set(bytes.subarray(entry.start, entry.start + entry.compressed), entry.packed);
      delete entry.start;
    }
    return { document, files, packed };
  } catch (error) {
    if (error instanceof ShareError) throw error;
    throw new ShareError(400, "INVALID_ARCHIVE", "Could not read the publication ZIP");
  }
}
