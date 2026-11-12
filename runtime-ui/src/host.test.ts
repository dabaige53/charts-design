import { expect, it, mock, spyOn } from "bun:test";
import { deliverExport } from "./host";

// @wu-test type=regression | scope=deliverExport | protects=防止 audit-1 复发：只读导出调用被禁止的原始文件读取接口
it("downloads the signed export URL when a chunk reader is also available", async () => {
  const fetcher = spyOn(globalThis, "fetch").mockResolvedValue(new Response("saved content"));
  const download = mock(async (_file: { name: string; mimeType: string; blob: Blob }) => {});
  const read = mock(async () => { throw Error("raw export read is forbidden"); });
  try {
    await deliverExport({
      id: "export-id", bytes: 13, filename: "saved.json",
      mimeType: "application/json", downloadUrl: "https://example.invalid/signed",
    }, download, read);
    expect(fetcher).toHaveBeenCalledWith("https://example.invalid/signed");
    expect(read).not.toHaveBeenCalled();
    expect(download).toHaveBeenCalledTimes(1);
    expect(await download.mock.calls[0][0].blob.text()).toBe("saved content");
  } finally {
    fetcher.mockRestore();
  }
});
