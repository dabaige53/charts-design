import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import type { Document } from "./types";

const originalFetch = globalThis.fetch;
const originalBoot = window.__chartsBoot;
const webGlobals = ["location", "history", "sessionStorage"] as const;
const originalGlobals = webGlobals.map(key => Object.getOwnPropertyDescriptor(globalThis, key));
afterEach(() => {
  globalThis.fetch = originalFetch;
  window.__chartsBoot = originalBoot;
  window.sessionStorage.clear();
  webGlobals.forEach((key, index) => {
    const descriptor = originalGlobals[index];
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else Reflect.deleteProperty(globalThis, key);
  });
});

// @wu-test type=integration | scope=在线访问令牌恢复 | protects=跳转丢失令牌后无法通过完整链接加载看板
it("retries dashboard loading with the pasted token after unauthorized", async () => {
  for (const key of webGlobals)
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value: window[key] });
  window.__chartsBoot = { mode: "web", projectRoot: "test", dashboardId: "board", apiBase: "/api/v1/p/test/tools/", idleTimeout: null, readOnly: true };
  document.body.innerHTML = '<div id="root"></div>';
  const dashboard: Document = {
    id: "board", revision: 1,
    manifest: { title: "已恢复的看板", viewMode: "report", report: { markdown: "" },
      components: {}, filters: [], layout: {}, metrics: {}, datasets: {} },
    snapshot: { datasets: {} },
  };
  const fetchMock = mock(async (url: RequestInfo | URL, init?: RequestInit) => {
    const authorization = new Headers(init?.headers).get("Authorization");
    if (authorization !== "Bearer restored-token")
      return new Response(JSON.stringify({ error: { code: "UNAUTHORIZED" } }), { status: 401 });
    return Response.json(String(url).endsWith("/dashboard_list")
      ? { dashboards: [{ id: "board" }], projectRoot: "test" }
      : { document: dashboard, projectRoot: "test" });
  });
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  await act(async () => { await import("./main"); });
  const input = await screen.findByLabelText("完整在线访问链接");
  fireEvent.change(input, { target: { value: `${window.location.origin}${window.location.pathname}#token=restored-token` } });
  fireEvent.click(screen.getByRole("button", { name: "打开看板" }));
  await screen.findByRole("heading", { name: "已恢复的看板" });
  expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/dashboard_preview"))).toHaveLength(1);
});
