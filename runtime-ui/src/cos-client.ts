import { createStaticClient } from "../../dashboard_runtime/web/static-client.mjs";
import { createStaticQuery } from "../../dashboard_runtime/web/static-query.mjs";
import type { Config, Document, ToolCall } from "./types";

export function createVersionReader(doc: Document, workerUrl: string, headers: Record<string, string> = {}) {
  const worker = doc.staticFiles
    ? createStaticClient(doc, location.href, workerUrl, Worker, headers)
    : null;
  const embedded = worker ? null : createStaticQuery(doc, async () => { throw Error("版本数据文件不存在"); });
  const query = (args: Config) => worker ? worker.query(args) : embedded!.query(args);
  const call: ToolCall = async (name, args = {}) => {
    if (args.expectedRevision != null && args.expectedRevision !== doc.revision)
      throw Error("版本已切换，请重新读取");
    if (name === "dashboard_list") return { dashboards: [{ id: doc.id, title: doc.manifest.title }] };
    if (name === "dashboard_get" || name === "dashboard_preview") return { document: doc };
    if (name === "runtime_info") return { dashboardRevision: doc.revision };
    if (name === "dashboard_view") return query(args);
    if (name === "dashboard_filter_options") return query({ ...args, filters: [] });
    if (name === "component_data") return query({ ...args, detail: true });
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
  return { call, destroy: () => worker?.destroy() };
}

export function createCosTools(remote: ToolCall, workerUrl: string, headers: () => Record<string, string>) {
  const readers = new Map<string, ReturnType<typeof createVersionReader>>();
  const keys = new Map<string, string>();
  const localTools = new Set(["dashboard_view", "dashboard_filter_options", "component_data", "dataset_export", "semantic_inspect"]);
  const call: ToolCall = async (name, args = {}) => {
    const reader = readers.get(args.dashboardId);
    if (reader && localTools.has(name)) return reader.call(name, args);
    const result = await remote(name, args);
    const doc = result.document as Document | undefined;
    if (doc?.storageFormat === "cos-v1") {
      const key = JSON.stringify([headers(), doc.versionKey, doc.manifest, doc.staticFiles]);
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
