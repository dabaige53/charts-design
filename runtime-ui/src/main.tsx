import { Component, useEffect, useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@modelcontextprotocol/ext-apps";
import { Toaster } from "sonner";
import { DashboardApp } from "./dashboard";
import { SnapshotApp, StaticSite } from "./static";
import { RecoveryAlert } from "./recovery-alert";
import { TooltipProvider } from "./components/ui/tooltip";
import { createProjectContext } from "./project-context.mjs";
import { resolveToolResult } from "./tool-result.mjs";
import { createRequestQueue } from "../../dashboard_runtime/web/request-queue.mjs";
import { browserDownload, type Download } from "./host";
import { WebAccess } from "./web-access";
import { createCosTools } from "./cos-client";
import type { Config, Document, ToolCall } from "./types";
const boot = window.__chartsBoot || { mode: "mcp" };
let app: App | undefined;
const webTokenKey = `charts-design-token:${boot.apiBase || "/api/tools/"}:${boot.projectRoot || ""}:${boot.dashboardId || ""}`;
function readWebToken() {
  if (boot.mode !== "web") return "";
  const stored = sessionStorage.getItem(webTokenKey) || "";
  const fragment = location.hash.slice(1);
  const token =
    new URLSearchParams(fragment).get("token") ||
    (!stored && /^[A-Za-z0-9_.-]{33,}$/.test(fragment) ? fragment : "");
  if (token) {
    sessionStorage.setItem(webTokenKey, token);
    history.replaceState(history.state, "", location.pathname + location.search);
  }
  return token || stored;
}
let webToken = readWebToken();
class WebAuthError extends Error {}
const queue = createRequestQueue(4);
// Editors immediately consume the updated document; Agent calls default to receipts.
const documentWrites = new Set([
  "dashboard_create", "dashboard_patch", "dashboard_restore",
  "dataset_import", "dataset_attach", "query_execute",
  "dashboard_migrate", "dashboard_migration_rollback",
]);
const send = (name: string, args: Config) =>
  queue(async () => {
    if (boot.mode === "mcp") {
      if (!app) throw Error("MCP 宿主尚未连接");
      return app.callServerTool({
        name,
        arguments: documentWrites.has(name) ? { ...args, responseMode: "full" } : args,
      });
    }
    const response = await fetch((boot.apiBase || "/api/tools/") + name, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + webToken,
      },
      body: JSON.stringify(args),
    });
    const value = await response.json();
    if (response.status === 401) throw new WebAuthError();
    if (!response.ok) throw Object.assign(Error(value.error?.message || "请求失败"), { code: value.error?.code });
    return value;
  });
const context = createProjectContext(send);
const remoteCall: ToolCall = async (name, args = {}) =>
  resolveToolResult(
    await context.call(name, args),
    (name: string, args: Config) => context.call(name, args),
  );
const cosTools = createCosTools(remoteCall, (boot.apiBase || "").split("/api/")[0] + "/assets/static-worker.js",
  () => ({ Authorization: "Bearer " + webToken }));
const call: ToolCall = boot.mode === "web" ? cosTools.call : remoteCall;
const download: Download = async (file) => {
  if (boot.mode !== "mcp") return browserDownload(file);
  if (!app?.getHostCapabilities()?.downloadFile)
    throw Error("当前 MCP 宿主不支持文件下载。文件仍保存在项目导出目录。");
  const bytes = new Uint8Array(await file.blob.arrayBuffer());
  let content = "";
  for (let offset = 0; offset < bytes.length; offset += 16384)
    content += String.fromCharCode(...bytes.subarray(offset, offset + 16384));
  const result = await app.downloadFile({
    contents: [
      {
        type: "resource",
        resource: {
          uri: "file:///" + encodeURIComponent(file.name),
          mimeType: file.mimeType,
          blob: btoa(content),
        },
      },
    ],
  });
  if (result.isError) throw Error("宿主未完成下载，请重新操作。");
};
class RenderBoundary extends Component<
  { children: ReactNode },
  { error: string }
> {
  state = { error: "" };
  static getDerivedStateFromError(error: Error) {
    return { error: error.message || String(error) };
  }
  render() {
    if (this.state.error)
      return (
        <RecoveryAlert
          className="m-6"
          title="页面暂时无法显示"
          message={this.state.error}
          retryLabel="重新打开页面"
          onRetry={() => location.reload()}
        />
      );
    return this.props.children;
  }
}
function Root() {
  const [doc, setDoc] = useState<Document | null>(boot.document || null),
    [error, setError] = useState(""),
    [accessRequired, setAccessRequired] = useState(false),
    [attempt, setAttempt] = useState(0),
    [fullscreen, setFullscreen] = useState(false),
    [hostFullscreen, setHostFullscreen] = useState(false);
  useEffect(() => {
    if (boot.mode === "snapshot" || boot.mode === "static") return;
    setError("");
    let live = true;
    const receive = async (result: any) => {
      try {
        context.accept(result);
        const value = await resolveToolResult(
          result,
          (name: string, args: Config) => context.call(name, args),
        );
        if (live && value.document) {
          setError("");
          setDoc((current) =>
            current &&
            current.id === value.document.id &&
            current.revision > value.document.revision
              ? current
              : value.document,
          );
        }
      } catch (e) {
        if (live) {
          if (e instanceof WebAuthError) setAccessRequired(true);
          else setError(String(e));
        }
      }
    };
    if (boot.mode === "mcp") {
      app = new App(
        { name: "charts-design UI", version: "0.1.0" },
        { availableDisplayModes: ["inline", "fullscreen"] },
      );
      app.ontoolresult = receive;
      app.onteardown = async () => {
        live = false;
        return {};
      };
      app.onhostcontextchanged = () => {
        setHostFullscreen(app?.getHostContext()?.displayMode === "fullscreen");
        setFullscreen(
          !!app
            ?.getHostContext()
            ?.availableDisplayModes?.includes("fullscreen"),
        );
      };
      void app
        .connect()
        .then(() => {
          if (live) {
            setHostFullscreen(app?.getHostContext()?.displayMode === "fullscreen");
            setFullscreen(
              !!app
                ?.getHostContext()
                ?.availableDisplayModes?.includes("fullscreen"),
            );
          }
        })
        .catch((e) => {
          if (live) setError(String(e));
        });
    } else {
      context.accept({ projectRoot: boot.projectRoot ?? null });
      setFullscreen(document.fullscreenEnabled);
      if (!boot.document)
        void call("dashboard_list")
          .then(async (result: Config) => {
            const id =
              boot.dashboardId ||
              new URLSearchParams(location.search).get("dashboardId") ||
              result.dashboards[0]?.id;
            if (id)
              await receive(
                await call("dashboard_preview", { dashboardId: id }),
              );
            else if (live)
              setError("尚无已保存的看板，请通过本项目 MCP 创建。");
          })
          .catch((e) => {
            if (live) {
              if (e instanceof WebAuthError) setAccessRequired(true);
              else setError(String(e));
            }
          });
    }
    return () => {
      live = false;
      void app?.close();
    };
  }, [attempt]);
  useEffect(() => {
    if (
      !doc ||
      boot.mode === "snapshot" ||
      boot.mode === "static" ||
      boot.idleTimeout === null
    )
      return;
    const interval = setInterval(() => {
      if (document.visibilityState === "visible")
        void call("runtime_keepalive").catch((e) => setError(String(e)));
    }, 20000);
    return () => clearInterval(interval);
  }, [!!doc]);
  window.__chartsReady = async () => {
    await document.fonts.ready;
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
  };
  if (boot.mode === "snapshot") return <SnapshotApp document={boot.document} />;
  if (boot.mode === "static") return <StaticSite />;
  if (accessRequired && !doc) return <WebAccess onAccess={(token) => {
    cosTools.destroy();
    webToken = token;
    sessionStorage.setItem(webTokenKey, token);
    setAccessRequired(false);
    setAttempt((value) => value + 1);
  }} />;
  if (error && !doc)
    return (
      <RecoveryAlert
        className="m-6"
        title="看板数据未能加载"
        message={error}
        onRetry={() => setAttempt((value) => value + 1)}
        retryLabel="重新连接并加载"
      />
    );
  if (!doc)
    return (
      <p role="status" className="p-8 text-muted-foreground">
        正在等待本项目 MCP 的看板数据…
      </p>
    );
  const full = fullscreen
    ? () => {
        const action = app
          ? app.requestDisplayMode({
              mode:
                app.getHostContext()?.displayMode === "fullscreen"
                  ? "inline"
                  : "fullscreen",
            })
          : document.fullscreenElement
            ? document.exitFullscreen()
            : document.documentElement.requestFullscreen();
        void action.catch((e) => setError(String(e)));
      }
    : undefined;
  return (
    <>
    {error && <RecoveryAlert className="m-4" title="操作未完成" message={error} onRetry={() => setError("")} retryLabel="返回看板" />}
    <DashboardApp
      buildId={boot.uiBuildId}
      initial={doc}
      call={call}
      download={download}
      readOnly={!!boot.readOnly}
      onFullscreen={full}
      pageFullscreen={hostFullscreen}
      primaryFilterIds={boot.primaryFilterIds}
      projectRoot={context.projectRoot}
    />
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <RenderBoundary>
    <TooltipProvider>
      <Root />
      <Toaster closeButton />
    </TooltipProvider>
  </RenderBoundary>,
);
