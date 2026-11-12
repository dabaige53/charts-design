import { afterEach, expect, it, mock } from "bun:test";
import { createStaticResources } from "../../dashboard_runtime/web/static-resources.mjs";
import { createStaticQuery } from "../../dashboard_runtime/web/static-query.mjs";
import { createVersionReader, loadWebDashboard } from "./cos-client";
import type { Config, Document } from "./types";

const originalFetch = globalThis.fetch;
const originalWorker = globalThis.Worker;
afterEach(() => {
  globalThis.fetch = originalFetch;
  globalThis.Worker = originalWorker;
});

function saved(): Document {
  return {
    id: "board", revision: 3, storageFormat: "cos-v1", browserDataUrl: "/content/board/3",
    manifest: {
      title: "Saved", filters: [], layout: {}, metrics: {},
      components: { table: { kind: "table", title: "Rows", datasetId: "sales" } },
      datasets: { sales: { fields: { value: { type: "number" } } } },
    },
    snapshot: { datasets: {} },
    computed: { components: { table: { rows: [{ value: 7 }] } }, tables: {} },
  };
}

// @wu-test type=behavior | scope=loadWebDashboard | protects=指定看板首屏被列表请求阻塞或错误加载其他看板
it("opens the requested saved dashboard without requesting its catalog", async () => {
  const doc = saved();
  const call = mock(async (name: string, _args?: Config) => {
    if (name === "dashboard_list") throw Error("Catalog unavailable");
    return { document: doc };
  });
  const result = await loadWebDashboard(call, "board");
  expect(result.document).toBe(doc);
  expect(call.mock.calls).toEqual([["dashboard_preview", { dashboardId: "board" }]]);
});

// @wu-test type=behavior | scope=loadWebDashboard | protects=未指定看板时丢失页面选择或重复获取已取得的列表
it("returns the catalog for reuse when selecting the first dashboard", async () => {
  const dashboards = [{ id: "board", title: "Saved" }];
  const call = mock(async (name: string, _args?: Config) => name === "dashboard_list" ? { dashboards } : { document: saved() });
  const result = await loadWebDashboard(call);
  expect(result.initialBoards).toBe(dashboards);
  expect(call.mock.calls).toEqual([["dashboard_list"], ["dashboard_preview", { dashboardId: "board" }]]);
});

// @wu-test type=integration | scope=createVersionReader deferred data | protects=显示保存结果时下载业务数据或并发交互重复加载数据目录
it("renders saved results without loading files and shares one directory request across queries", async () => {
  Object.assign(globalThis, { location: window.location });
  const doc = saved(), files: string[] = [];
  let workers = 0;
  class QueryWorker {
    engine: any;
    resources = createStaticResources({fetcher: async (url: string) => {
      files.push(new URL(url).pathname.split("/").pop()!);
      return new Response(JSON.stringify([{ value: 7 }, { value: 9 }]));
    }});
    onmessage: any;
    terminated = false;
    constructor() { workers++; }
    postMessage({ id, type, args }: any) {
      if (!["init", "query"].includes(type)) return;
      void Promise.resolve().then(async () => {
        if (type === "init") {
          this.engine = createStaticQuery(args.document, (file: string) => this.resources.json(new URL(file, args.base).href));
          return { ready: true };
        }
        return this.engine.query(args);
      }).then(result => { if (!this.terminated) this.onmessage({ data: { id, result } }); });
    }
    terminate() { this.terminated = true; }
  }
  globalThis.Worker = QueryWorker as any;
  const fetcher = mock(async () => new Response(JSON.stringify({
    id: "board", revision: 3, staticFiles: { sales: ["rows.json"] },
  })));
  globalThis.fetch = fetcher as unknown as typeof fetch;
  const reader = createVersionReader(doc, "/worker.js", { Authorization: "Bearer test" });
  try {
    expect((await reader.call("dashboard_preview")).document).toBe(doc);
    expect(fetcher).not.toHaveBeenCalled();
    expect(workers).toBe(0);
    const [first, second] = await Promise.all([
      reader.call("dashboard_view", { expectedRevision: 3, componentIds: ["table"] }),
      reader.call("component_data", { expectedRevision: 3, componentId: "table" }),
    ]);
    expect(first.computed.components.table.rows).toEqual([{ value: 7 }, { value: 9 }]);
    expect(second.totalRows).toBe(2);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(workers).toBe(1);
    expect(files).toEqual(["rows.json"]);
    await expect(reader.call("dashboard_view", { expectedRevision: 2 })).rejects.toThrow("版本已切换");
  } finally { reader.destroy(); }
});

// @wu-test type=boundary | scope=createVersionReader data directory | protects=错误版本目录被用于当前数据计算或失败目录无法重试
it("rejects a mismatched directory and retries without losing saved content", async () => {
  Object.assign(globalThis, { location: window.location });
  const doc = saved();
  const fetcher = mock(async () => new Response(JSON.stringify({ id: "board", revision: 4, staticFiles: {} })));
  globalThis.fetch = fetcher as unknown as typeof fetch;
  const reader = createVersionReader(doc, "/worker.js");
  try {
    await expect(reader.call("dashboard_view")).rejects.toThrow("数据目录与当前看板版本不一致");
    await expect(reader.call("dashboard_view")).rejects.toThrow("数据目录与当前看板版本不一致");
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect((await reader.call("dashboard_preview")).document.computed).toBe(doc.computed);
  } finally { reader.destroy(); }
});

// @wu-test type=boundary | scope=createVersionReader lifecycle | protects=版本切换后旧目录响应重新启动已关闭的数据读取器
it("aborts the directory request and rejects a response arriving after the reader closes", async () => {
  Object.assign(globalThis, { location: window.location });
  let respond!: (response: Response) => void;
  let signal: AbortSignal | undefined;
  globalThis.fetch = mock((_url: any, options: any) => {
    signal = options.signal;
    return new Promise<Response>(resolve => { respond = resolve; });
  }) as unknown as typeof fetch;
  const reader = createVersionReader(saved(), "/worker.js");
  const pending = reader.call("dashboard_view").catch(error => error);
  reader.destroy();
  expect(signal?.aborted).toBe(true);
  respond(new Response(JSON.stringify({ id: "board", revision: 3, staticFiles: {} })));
  expect((await pending).message).toBe("页面已关闭");
});
