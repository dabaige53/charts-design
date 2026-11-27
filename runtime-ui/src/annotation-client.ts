import type { AnnotationAccess, Config, ToolCall } from "./types";

/** Annotation storage is an HTTP capability, separate from the content tool transport. */
export function createAnnotationClient(
  access: AnnotationAccess,
  revision: () => number,
  headers: () => Record<string, string> = () => ({}),
): ToolCall {
  return async (name, args = {}) => {
    const writing = name === "dashboard_annotations_update";
    if (name !== "dashboard_annotations" && !writing) throw Error("此入口仅支持批注");
    if (!access.canRead || (writing && !access.canAnnotate)) throw Error("此链接没有提交批注的权限");
    if (writing && !args.append && !access.canManageAnnotations) throw Error("此链接仅允许新增批注");
    const endpoint = new URL(access.endpoint.replace("{dashboardId}", encodeURIComponent(args.dashboardId)), location.href);
    // A document must never redirect an author token to another origin.
    if (endpoint.origin !== location.origin) throw Error("批注服务须与当前页面同源");
    const targetRevision = revision();
    const request: RequestInit = { credentials: "same-origin", cache: "no-store", headers: headers() };
    if (writing) {
      const body: Config = { ...args, revision: targetRevision };
      if (body.append?.authorName !== undefined) {
        const { authorName, ...note } = body.append;
        body.append = note;
        body.authorName = authorName;
      }
      request.method = "POST";
      request.headers = { ...request.headers, "Content-Type": "application/json" };
      request.body = JSON.stringify(body);
    } else {
      endpoint.searchParams.set("dashboardId", args.dashboardId);
      endpoint.searchParams.set("revision", String(targetRevision));
    }
    const response = await fetch(endpoint, request);
    let value: Config;
    try { value = await response.json(); }
    catch { throw Error(`批注服务未返回可用结果（${response.status}）`); }
    if (!response.ok || value.ok === false) {
      const message = value.error?.message || value.message || (response.status === 401
        ? "访问已失效，请重新打开收到的链接" : "批注保存或读取失败");
      throw Object.assign(Error(message), { code: value.error?.code || value.code });
    }
    if (writing && args.append && !value.annotation) throw Error("批注未确认保存；请重试本条批注");
    if (!writing && !Array.isArray(value.annotations)) throw Error("无法读取批注列表");
    return { ...value, independentSave: true };
  };
}
