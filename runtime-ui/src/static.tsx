import { useEffect, useState } from "react";
import { createStaticClient } from "../../dashboard_runtime/web/static-client.mjs";
import { DashboardApp } from "./dashboard";
import { DashboardGrid } from "./grid";
import { ComponentView } from "./component-view";
import { ReportView } from "./report";
import { Alert, AlertDescription } from "./components/ui/alert";
import type { Document, ToolCall } from "./types";

export function SnapshotApp({ document: doc }: { document: Document }) {
  const component = (id: string) => <ComponentView document={doc} id={id} />;
  return (
    <main className="p-6">
      <h1 className="mb-2 text-2xl font-medium text-brand">
        {doc.manifest.title}
      </h1>
      <p className="mb-5 text-sm text-muted-foreground">
        当前视图快照 · 版本 {doc.revision}
      </p>
      {doc.manifest.viewMode === "report" ? (
        <ReportView document={doc} component={component} />
      ) : (
        <DashboardGrid document={doc} editing={false} onLayoutChange={() => {}}>
          {component}
        </DashboardGrid>
      )}
    </main>
  );
}
export function StaticSite() {
  const [state, setState] = useState<{ doc: Document; call: ToolCall } | null>(
      null,
    ),
    [error, setError] = useState("");
  useEffect(() => {
    let live = true,
      client: ReturnType<typeof createStaticClient> | undefined;
    void fetch(new URL("document.json", location.href))
      .then(async (response) => {
        if (!response.ok) throw Error(`网页数据加载失败（${response.status}）`);
        const doc = (await response.json()) as Document;
        client = createStaticClient(doc, location.href, "static-worker.js");
        const query = client;
        const call: ToolCall = async (name, args = {}) => {
          if (name === "dashboard_list")
            return { dashboards: [{ id: doc.id, title: doc.manifest.title }] };
          if (name === "dashboard_get" || name === "dashboard_preview")
            return { document: doc };
          if (name === "runtime_info")
            return { dashboardRevision: doc.revision };
          if (name === "dashboard_view") return query.query(args);
          if (name === "dashboard_filter_options")
            return query.query({ ...args, filters: [] });
          if (name === "semantic_inspect") {
            const component = doc.manifest.components[args.componentId],
              ids = component.binding
                ? Object.values(component.binding.measures)
                : component.measures || [];
            return {
              component,
              metrics: Object.fromEntries(
                ids.map((id: any) => [id, doc.manifest.metrics[id]]),
              ),
            };
          }
          if (name === "dataset_export") {
            const result = await query.query({
              ...args,
              componentIds: [args.componentId],
              export: { columns: args.columns },
              tableStates: {
                [args.componentId]: {
                  keyword: args.search,
                  sortCol: args.sort?.[0]?.field,
                  sortDir: args.sort?.[0]?.direction,
                },
              },
            });
            const bytes = new TextEncoder().encode("\ufeff" + result.csv);
            let text = "";
            for (let offset = 0; offset < bytes.length; offset += 16384)
              text += String.fromCharCode(
                ...bytes.subarray(offset, offset + 16384),
              );
            return {
              export: {
                filename: args.componentId + ".csv",
                mimeType: "text/csv",
                content: btoa(text),
              },
            };
          }
          throw Error("独立静态网页不支持此操作。请回到本项目 MCP。");
        };
        if (live) setState({ doc, call });
      })
      .catch((e) => {
        if (live) setError(String(e));
      });
    return () => {
      live = false;
      client?.destroy();
    };
  }, []);
  if (error)
    return (
      <Alert variant="destructive">
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  if (!state)
    return (
      <p role="status" className="p-6">
        正在加载网页…
      </p>
    );
  return (
    <DashboardApp
      initial={state.doc}
      call={state.call}
      readOnly
      staticMode
      onFullscreen={
        document.fullscreenEnabled
          ? () => {
              const action = document.fullscreenElement
                ? document.exitFullscreen()
                : document.documentElement.requestFullscreen();
              void action.catch((error) => setError(String(error)));
            }
          : undefined
      }
    />
  );
}
