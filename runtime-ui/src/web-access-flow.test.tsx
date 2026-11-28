import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import type { Document } from "./types";

const originalFetch = globalThis.fetch;
const originalBoot = window.__chartsBoot;
const webGlobals = ["location", "history", "sessionStorage"] as const;
const originalGlobals = webGlobals.map(key => Object.getOwnPropertyDescriptor(globalThis, key));
let applicationRoot: { unmount: () => void } | undefined;
afterEach(() => {
  act(() => applicationRoot?.unmount());
  applicationRoot = undefined;
  document.body.innerHTML = "";
  globalThis.fetch = originalFetch;
  window.__chartsBoot = originalBoot;
  window.sessionStorage.clear();
  webGlobals.forEach((key, index) => {
    const descriptor = originalGlobals[index];
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else Reflect.deleteProperty(globalThis, key);
  });
});

// @wu-test type=integration | scope=在线访问令牌恢复 | protects=跳转丢失令牌后无法恢复报告或用已知看板 ID 仍查询看板列表
it("retries report loading with the pasted token after unauthorized", async () => {
  for (const key of webGlobals)
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value: window[key] });
  window.__chartsBoot = { mode: "web", projectRoot: "test", dashboardId: "board", apiBase: "/api/v1/p/test/tools/", idleTimeout: null, readOnly: true };
  document.body.innerHTML = '<div id="root"></div>';
  const dashboard: Document = {
    id: "board", revision: 1,
    manifest: { title: "已恢复的报告", viewMode: "report", report: { markdown: "# 已恢复的报告" },
      components: {}, filters: [], layout: {}, metrics: {}, datasets: {} },
    snapshot: { datasets: {} },
  };
  const fetchMock = mock(async (_url: RequestInfo | URL, init?: RequestInit) => {
    const authorization = new Headers(init?.headers).get("Authorization");
    if (authorization !== "Bearer restored-token")
      return new Response(JSON.stringify({ error: { code: "UNAUTHORIZED" } }), { status: 401 });
    return Response.json({ document: dashboard, projectRoot: "test" });
  });
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  await act(async () => { applicationRoot = (await import("./main")).applicationRoot; });
  const input = await screen.findByLabelText("完整在线访问链接");
  fireEvent.change(input, { target: { value: `${window.location.origin}${window.location.pathname}#token=restored-token` } });
  fireEvent.click(screen.getByRole("button", { name: "打开看板" }));
  await screen.findByRole("heading", { name: "已恢复的报告" });
  const requests = fetchMock.mock.calls.map(([url, init]) => ({
    url: String(url),
    restored: new Headers(init?.headers).get("Authorization") === "Bearer restored-token",
  }));
  expect(requests).toEqual([
    { url: "/api/v1/p/test/tools/dashboard_preview", restored: false },
    { url: "/api/v1/p/test/tools/dashboard_preview", restored: true },
  ]);
});
