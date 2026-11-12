import { createStaticClient } from "../../dashboard_runtime/web/static-client.mjs";
import { createStaticQuery } from "../../dashboard_runtime/web/static-query.mjs";
import type { Config, Document, ToolCall } from "./types";

export async function loadWebDashboard(call: ToolCall, dashboardId?: string): Promise<Config & { initialBoards?: Config[] }> {
  const catalog = dashboardId ? undefined : await call("dashboard_list");
  const id = dashboardId || catalog?.dashboards[0]?.id;
  if (!id) throw Error("尚无已保存的看板，请通过本项目 MCP 创建。");
  return { ...await call("dashboard_preview", { dashboardId: id }), initialBoards: catalog?.dashboards };
}

export function createVersionReader(doc: Document, workerUrl: string, headers: Record<string, string> = {}) {
  let worker = doc.staticFiles && !doc.browserDataUrl
    ? createStaticClient(doc, location.href, workerUrl, Worker, headers)
    : null;
  const embedded = worker || doc.browserDataUrl ? null : createStaticQuery(doc, async () => { throw Error("版本数据文件不存在"); });
  let preparing: Promise<void> | undefined;
  let closed = false;
  const controller = new AbortController();
  const query = async (args: Config, options?: { signal?: AbortSignal }) => {
    options?.signal?.throwIfAborted();
    if (closed) throw Object.assign(Error("页面已关闭"), { name: "AbortError" });
    if (doc.browserDataUrl && !worker) {
      preparing ??= (async () => {
        const response = await fetch(new URL(doc.browserDataUrl, location.href), { headers, signal: controller.signal });
        if (!response.ok) throw Error(`数据目录加载失败（${response.status}）`);
        const data = await response.json();
        if (data.id !== doc.id || data.revision !== doc.revision || !data.staticFiles)
          throw Error("数据目录与当前看板版本不一致，请刷新。");
        if (closed) throw Object.assign(Error("页面已关闭"), { name: "AbortError" });
        worker = createStaticClient({ ...doc, ...data }, location.href, workerUrl, Worker, headers);
      })().catch(error => { preparing = undefined; throw error; });
      await preparing;
    }
    return worker ? worker.query(args, options) : embedded!.query(args, options);
  };
  const call: ToolCall = async (name, args = {}, options) => {
    if (args.expectedRevision != null && args.expectedRevision !== doc.revision)
      throw Error("版本已切换，请重新读取");
    if (name === "dashboard_list") return { dashboards: [{ id: doc.id, title: doc.manifest.title }] };
    if (name === "dashboard_get" || name === "dashboard_preview") return { document: doc };
    if (name === "runtime_info") return { dashboardRevision: doc.revision };
    if (name === "dashboard_view") return query(args, options);
    if (name === "dashboard_filter_options") return query({ ...args, filters: [] }, options);
    if (name === "component_data") return query({ ...args, detail: true }, options);
    if (name === "semantic_inspect") {
      const component = doc.manifest.components[args.componentId];
      const ids: string[] = component.binding ? Object.values(component.binding.measures) : component.measures || [];
      return { component, metrics: Object.fromEntries(ids.map((id) => [id, doc.manifest.metrics[id]])) };
    }
    if (name === "dataset_export") {
      const componentId = args.componentId || Object.keys(doc.manifest.components).find(id => doc.manifest.components[id].datasetId === args.datasetId);
      if (!componentId) throw Error("请选择包含此数据集的组件");
      const component = doc.manifest.components[componentId];
      const presentation = { ...component.presentation, ...component.config };
      const result = presentation.groupBy
        ? await query({ ...args, componentIds: [componentId], export: { columns: args.columns, fieldNames: true },
            tableStates: { [componentId]: { keyword: args.search, sortCol: args.sort?.[0]?.field, sortDir: args.sort?.[0]?.direction } } })
        : await query({ ...args, componentId, detail: true, export: true });
      const bytes = new TextEncoder().encode(result.csv);
      let binary = "";
      for (let offset = 0; offset < bytes.length; offset += 16384)
        binary += String.fromCharCode(...bytes.subarray(offset, offset + 16384));
      return { export: { filename: (componentId || "data") + ".csv", mimeType: "text/csv", content: btoa(binary) } };
    }
    throw Error("历史版本为只读内容，不支持此操作");
  };
  return { call, destroy: () => { closed = true; controller.abort(); worker?.destroy(); } };
}

export function createCosTools(remote: ToolCall, workerUrl: string, headers: () => Record<string, string>) {
  const readers = new Map<string, ReturnType<typeof createVersionReader>>();
  const keys = new Map<string, string>();
  const localTools = new Set(["dashboard_view", "dashboard_filter_options", "component_data", "dataset_export", "semantic_inspect"]);
  const call: ToolCall = async (name, args = {}, options) => {
    const reader = readers.get(args.dashboardId);
    if (reader && localTools.has(name)) return reader.call(name, args, options);
    const result = await remote(name, args, options);
    const doc = result.document as Document | undefined;
    if (doc?.storageFormat === "cos-v1") {
      const key = JSON.stringify([headers(), doc.versionKey, doc.manifest, doc.staticFiles, doc.browserDataUrl]);
      if (keys.get(doc.id) !== key) {
        readers.get(doc.id)?.destroy();
        readers.set(doc.id, createVersionReader(doc, workerUrl, headers()));
        keys.set(doc.id, key);
      }
    }
    return result;
  };
  return { call, destroy: () => { readers.forEach(reader => reader.destroy()); readers.clear(); keys.clear(); } };
}
