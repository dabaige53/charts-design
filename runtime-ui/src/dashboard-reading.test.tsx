import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import { DashboardApp } from "./dashboard";
import { TooltipProvider } from "./components/ui/tooltip";
import type { Config, Document } from "./types";

afterEach(cleanup);

// @wu-test type=integration | scope=DashboardApp 阅读版本 | protects=筛选候选项与HTML导出遗漏页面版本，刷新后继续请求旧数据版本
it("pins filter loading and HTML export to the displayed revision across refresh", async () => {
  const descriptors = ["ResizeObserver", "NodeFilter", "location", "sessionStorage", "HTMLInputElement"].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)] as const);
  Object.defineProperty(globalThis, "ResizeObserver", { configurable: true, value: class {
    observe() {} unobserve() {} disconnect() {}
  } });
  for (const key of ["NodeFilter", "location", "sessionStorage", "HTMLInputElement"] as const)
    Object.defineProperty(globalThis, key, { configurable: true, value: window[key] });
  try {
    const initial: Document = {
      id: "reading", revision: 2, dataVersion: "data-two",
      manifest: { title: "读取一致性", viewMode: "report", report: { markdown: "" },
        components: {}, datasets: { sales: { fields: { region: { type: "string" } } } }, metrics: {}, layout: {},
        filters: [{ id: "region", label: "区域", field: "region", op: "in", values: [], componentIds: [] }] },
      snapshot: { datasets: {} },
    };
    const call = mock(async (name: string, _args: Config = {}) => {
      if (name === "dashboard_list") return { dashboards: [{ id: initial.id }] };
      if (name === "dashboard_filter_options") return { values: ["华东"], hasMore: false, totalValues: 1 };
      if (name === "dashboard_preview") return { document: { ...initial, revision: 3, dataVersion: "data-three" } };
      if (name === "dashboard_export") return { export: { filename: "reading.html", mimeType: "text/html", content: btoa("<html></html>") } };
      return {};
    });
    const download = mock(async () => {});
    const filterVersions = () => call.mock.calls.filter(([name]) => name === "dashboard_filter_options")
      .map(([, args]) => [args?.expectedRevision, args?.dataVersion]);
    render(<TooltipProvider><DashboardApp initial={initial} call={call} download={download} readOnly /></TooltipProvider>);
    fireEvent.click(screen.getByRole("combobox", { name: "区域" }));
    await waitFor(() => expect(filterVersions()).toContainEqual([2, "data-two"]));
    fireEvent.keyDown(screen.getByRole("combobox", { name: "区域" }), { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "导出 HTML" }));
    await waitFor(() => expect(download).toHaveBeenCalledTimes(1));
    expect(call.mock.calls.find(([name]) => name === "dashboard_export")?.[1]).toMatchObject({
      dashboardId: "reading", expectedRevision: 2, dataVersion: "data-two", format: "html",
    });
    fireEvent.click(screen.getByRole("button", { name: "刷新报表" }));
    await waitFor(() => expect(call.mock.calls.some(([name]) => name === "dashboard_preview")).toBe(true));
    // If the picker remained open it reloads itself; otherwise open it again.
    const picker = screen.getByRole("combobox", { name: "区域" });
    if (picker.getAttribute("aria-expanded") !== "true") fireEvent.click(picker);
    await waitFor(() => expect(filterVersions()).toContainEqual([3, "data-three"]));
  } finally {
    cleanup();
    for (const [key, descriptor] of descriptors) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else Reflect.deleteProperty(globalThis, key);
    }
  }
});
