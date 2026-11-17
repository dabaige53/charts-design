import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, mock } from "bun:test";
import { DashboardApp } from "./dashboard";
import { TooltipProvider } from "./components/ui/tooltip";
import type { Config, Document } from "./types";

const browserGlobals = Object.fromEntries(
  ["location", "sessionStorage", "ResizeObserver"].map(name => [name, Object.getOwnPropertyDescriptor(globalThis, name)]),
);
beforeEach(() => {
  Object.defineProperty(globalThis, "location", { configurable: true, value: window.location });
  Object.defineProperty(globalThis, "sessionStorage", { configurable: true, value: window.sessionStorage });
  Object.defineProperty(globalThis, "ResizeObserver", {
    configurable: true, value: class { observe() {} disconnect() {} },
  });
});
afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  for (const [name, descriptor] of Object.entries(browserGlobals)) {
    if (descriptor) Object.defineProperty(globalThis, name, descriptor);
    else Reflect.deleteProperty(globalThis, name);
  }
});

// @wu-test type=regression | scope=DashboardApp 布局编辑 | protects=layout-draft-mismatch-20261117：已有草稿使布局编辑永久被拦截或保存覆盖草稿标题
it("opens the latest draft and saves against its revision", async () => {
  const saved: Document = {
    id: "board", revision: 14, progressive: true,
    manifest: {
      title: "保存标题", viewMode: "report", report: { markdown: "" },
      components: {}, filters: [], layout: {}, metrics: {}, datasets: {},
    },
    snapshot: { datasets: {} },
  };
  const draft = { ...saved, revision: 15, manifest: { ...saved.manifest, title: "草稿标题" } };
  const patched = { ...draft, revision: 16 };
  const call = mock(async (name: string, args: Config = {}) => {
    if (name === "dashboard_get") return { document: call.mock.calls.some(([tool]) => tool === "dashboard_patch") ? patched : draft };
    if (name === "dashboard_edit_begin") return { batch_id: "batch" };
    if (name === "dashboard_patch") return { document: patched };
    if (name === "dashboard_edit_finish") return { ok: true };
    throw Error(`Unexpected tool: ${name}`);
  });
  render(<TooltipProvider><DashboardApp initial={saved} initialBoards={[]} call={call} /></TooltipProvider>);
  fireEvent.click(screen.getByRole("button", { name: "编辑布局" }));
  const title = await screen.findByRole("textbox", { name: "看板标题" });
  expect((title as HTMLInputElement).value).toBe("草稿标题");
  expect(screen.queryByText("部分数据或操作未能完成")).toBeNull();
  expect(call.mock.calls.map(([name]) => name)).toEqual(["dashboard_get"]);
  fireEvent.change(title, { target: { value: "调整后的草稿标题" } });
  fireEvent.click(screen.getByRole("button", { name: "保存布局" }));
  await waitFor(() => expect(call.mock.calls.some(([name]) => name === "dashboard_edit_finish")).toBe(true));
  expect(call.mock.calls.find(([name]) => name === "dashboard_edit_begin")?.[1]).toMatchObject({ expectedRevision: 15 });
  expect(call.mock.calls.find(([name]) => name === "dashboard_patch")?.[1]).toMatchObject({
    expectedRevision: 15,
    operations: expect.arrayContaining([expect.objectContaining({ op: "set_title", value: "调整后的草稿标题" })]),
  });
  await screen.findByRole("button", { name: "编辑布局" });
});
