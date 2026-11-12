import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, it, mock } from "bun:test";

mock.module("./dashboard", () => ({ DashboardApp: () => <p>看板已打开</p> }));
mock.module("./static", () => ({ SnapshotApp: () => null, StaticSite: () => null }));
mock.module("./components/ui/tooltip", () => ({ TooltipProvider: ({ children }: any) => children }));
mock.module("sonner", () => ({ Toaster: () => null }));

// @wu-test type=integration | scope=在线访问令牌恢复 | protects=跳转丢失令牌后无法通过完整链接加载看板
it("retries dashboard loading with the pasted token after unauthorized", async () => {
  Object.assign(globalThis, { location: window.location, history: window.history, sessionStorage: window.sessionStorage });
  window.__chartsBoot = { mode: "web", projectRoot: "test", dashboardId: "board", apiBase: "/api/v1/p/test/tools/" };
  document.body.innerHTML = '<div id="root"></div>';
  let calls = 0;
  globalThis.fetch = mock(async (_url, init) => {
    calls++;
    const authorization = (init?.headers as Record<string, string>).Authorization;
    if (authorization !== "Bearer restored-token")
      return new Response(JSON.stringify({ error: { code: "UNAUTHORIZED" } }), { status: 401 });
    return new Response(JSON.stringify(calls === 2
      ? { dashboards: [{ id: "board" }], projectRoot: "test" }
      : { document: { id: "board", revision: 1 }, projectRoot: "test" }), { status: 200 });
  }) as unknown as typeof fetch;
  await act(async () => { await import("./main"); });
  const input = await screen.findByLabelText("完整在线访问链接");
  fireEvent.change(input, { target: { value: `${window.location.origin}${window.location.pathname}#token=restored-token` } });
  fireEvent.click(screen.getByRole("button", { name: "打开看板" }));
  await waitFor(() => expect(screen.getByText("看板已打开")).toBeTruthy());
  expect(calls).toBe(3);
});
