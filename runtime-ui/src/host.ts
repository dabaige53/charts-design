import type { Config } from "./types";
export type Download = (file: {
  name: string;
  mimeType: string;
  blob: Blob;
}) => Promise<void>;
export async function browserDownload({
  name,
  blob,
}: {
  name: string;
  mimeType: string;
  blob: Blob;
}) {
  const url = URL.createObjectURL(blob),
    anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function csvBlob(headers: string[], rows: any[][]) {
  const cell = (v: any) => {
    const text = v == null ? "" : String(v);
    const safe =
      /^[=+@\-\t\r]/.test(text) && typeof v !== "number" ? "'" + text : text;
    return '"' + safe.replaceAll('"', '""') + '"';
  };
  return new Blob(
    [
      "\ufeff" +
        [headers, ...rows].map((row) => row.map(cell).join(",")).join("\r\n"),
    ],
    { type: "text/csv;charset=utf-8" },
  );
}
export async function deliverExport(
  value: Config,
  download: Download,
  read?: (offset: number, limit: number) => Promise<Config>,
) {
  if (value.id && read) {
    const size = 262144,
      total = value.bytes,
      parts = new Array<Uint8Array>(Math.ceil(total / size));
    let next = 0;
    const worker = async () => {
      while (next < parts.length) {
        const index = next++,
          offset = index * size,
          part = await read(offset, size);
        const bytes = Uint8Array.from(atob(part.content), (c) =>
          c.charCodeAt(0),
        );
        if (
          part.id !== value.id ||
          part.offset !== offset ||
          part.bytes !== total ||
          bytes.length !== Math.min(size, total - offset)
        )
          throw Error("导出文件分块不完整，请重新生成。");
        parts[index] = bytes;
      }
    };
    await Promise.all(
      Array.from({ length: Math.min(4, parts.length) }, worker),
    );
    await download({
      name: value.filename,
      mimeType: value.mimeType,
      blob: new Blob(parts as BlobPart[], { type: value.mimeType }),
    });
    return;
  }
  if (value.downloadUrl) {
    const response = await fetch(value.downloadUrl);
    if (!response.ok) throw Error("导出文件下载失败，请重新生成。");
    await download({
      name: value.filename ?? "export.csv",
      mimeType: value.mimeType,
      blob: await response.blob(),
    });
    return;
  }
  if (value.content) {
    const bytes = Uint8Array.from(atob(value.content), (c) => c.charCodeAt(0));
    await download({
      name: value.filename,
      mimeType: value.mimeType,
      blob: new Blob([bytes], { type: value.mimeType }),
    });
    return;
  }
  if (value.path)
    throw Error(`文件已保存在 ${value.path}。当前宿主不支持直接下载此文件。`);
  throw Error("导出结果中没有可下载的文件。");
}
