import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import { DashboardApp } from "./dashboard";
import { ComponentView } from "./component-view";
import { TooltipProvider } from "./components/ui/tooltip";
import type { Config, Document } from "./types";

afterEach(cleanup);

// @wu-test type=integration | scope=图表操作菜单 | protects=查看 SQL 显示错误数据集的语句或把参数值当作 SQL 展示
it("shows the SQL bound to the chart from its action menu", async () => {
  const initial: Document = {
    id: "sql", revision: 1,
    manifest: {
      title: "收入",
      components: { region: { kind: "legacy", family: "chart", title: "区域收入",
        datasetId: "sales", config: { code: "c01", data: {} } } },
      filters: [], layout: {}, metrics: {},
      datasets: { sales: { mode: "live", sourceId: "selected" } },
      sources: {
        unrelated: { query: { sql: "SELECT * FROM other" } },
        selected: { query: { sql: "SELECT * FROM sales WHERE region = :region", parameters: { region: "华东" } } },
      },
    },
    snapshot: { datasets: {} },
  };
  const descriptors = ["ResizeObserver", "NodeFilter", "HTMLInputElement"]
    .map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)] as const);
  Object.defineProperty(globalThis, "ResizeObserver", { configurable: true, value: class {
    observe() {} disconnect() {}
  } });
  for (const key of ["NodeFilter", "HTMLInputElement"] as const)
    Object.defineProperty(globalThis, key, { configurable: true, value: window[key] });
  try {
    render(<TooltipProvider><ComponentView document={initial} id="region" loading /></TooltipProvider>);
    fireEvent.keyDown(screen.getByRole("button", { name: "更多图表操作" }), { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("menuitem", { name: "查看 SQL" }));
    await screen.findByRole("dialog", { name: "查看 SQL" });
    expect(screen.getByText("SELECT * FROM sales WHERE region = :region")).toBeTruthy();
    expect(screen.queryByText("SELECT * FROM other")).toBeNull();
    expect(screen.queryByText("华东")).toBeNull();
  } finally {
    cleanup();
    for (const [key, descriptor] of descriptors) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else Reflect.deleteProperty(globalThis, key);
    }
  }
});

// @wu-test type=integration | scope=独立论文报告页 | protects=报告页携带看板筛选、导航、编辑和批注入口
it("renders an academic report without dashboard controls", () => {
  const initial: Document = {
    id: "paper", revision: 1,
    manifest: {
      title: "收入研究", viewMode: "report", report: { markdown: "# 收入研究\n\n研究结论" },
      components: {}, datasets: {}, metrics: {}, layout: {},
      filters: [{ id: "region", label: "区域", field: "region", op: "in", values: [], componentIds: [] }],
    },
    snapshot: { datasets: {} },
  };
  const call = mock(async () => ({}));
  render(<DashboardApp initial={initial} call={call} />);
  expect(screen.getByRole("main").classList.contains("analytical-report-page")).toBe(true);
  expect(screen.getAllByRole("heading", { name: "收入研究" })).toHaveLength(1);
  expect(screen.getByText("研究结论")).toBeTruthy();
  expect(screen.queryAllByRole("button")).toHaveLength(0);
  expect(screen.queryByRole("combobox")).toBeNull();
  expect(call).not.toHaveBeenCalled();
});

// @wu-test type=integration | scope=DashboardApp 阅读版本与筛选加载 | protects=首次展开等待搜索防抖、重复发送输入中间词或读取旧页面版本
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
      manifest: { title: "读取一致性", viewMode: "dashboard",
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
    expect(filterVersions()).toEqual([[2, "data-two"]]);
    await screen.findByRole("option", { name: "华东" });
    const search = screen.getByPlaceholderText("搜索选项");
    const searches = () => call.mock.calls
      .filter(([name, args]) => name === "dashboard_filter_options" && args?.search)
      .map(([, args]) => args?.search);
    fireEvent.change(search, { target: { value: "华" } });
    fireEvent.change(search, { target: { value: "华东" } });
    expect(searches()).toEqual([]);
    await waitFor(() => expect(searches()).toEqual(["华东"]));
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

// @wu-test type=boundary | scope=作者保存回读恢复 | protects=恢复新草稿后仍保留旧布局编辑器并在下一次点击覆盖新版本
it("leaves the stale layout editor after reconciling a failed save read", async () => {
  const descriptors = ["ResizeObserver", "NodeFilter", "location", "sessionStorage", "HTMLInputElement"].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)] as const);
  Object.defineProperty(globalThis, "ResizeObserver", { configurable: true, value: class {
    observe() {} unobserve() {} disconnect() {}
  } });
  for (const key of ["NodeFilter", "location", "sessionStorage", "HTMLInputElement"] as const)
    Object.defineProperty(globalThis, key, { configurable: true, value: window[key] });
  try {
    const initial: Document = {
      id: "save-recovery", revision: 1, progressive: true,
      manifest: { title: "初始标题", components: {}, datasets: {}, metrics: {}, layout: {}, filters: [] },
      snapshot: { datasets: {} },
    };
    let remote = initial, failRead = false;
    const submissions: Config[] = [];
    const call = mock(async (name: string, args: Config = {}) => {
      if (name === "dashboard_list") return { dashboards: [{ id: initial.id }] };
      if (name === "dashboard_submit") {
        submissions.push(args);
        remote = { ...remote, revision: remote.revision + 1 };
        failRead = submissions.length === 1;
        return { ok: true, revision: remote.revision };
      }
      if (name === "dashboard_get") {
        if (failRead) { failRead = false; throw Error("Temporary read failure"); }
        return { document: remote };
      }
      return {};
    });
    render(<TooltipProvider><DashboardApp initial={initial} call={call}
      annotationAccess={{ endpoint: "", canRead: false, canAnnotate: false, canManageAnnotations: false, scope: "test" }} /></TooltipProvider>);
    fireEvent.click(screen.getByRole("button", { name: "编辑布局" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "看板标题" }), { target: { value: "本次标题" } });
    fireEvent.click(screen.getByRole("button", { name: "保存布局" }));
    await screen.findByText(/只重新读取最新草稿并结束当前编辑/);
    remote = { ...remote, revision: 3, manifest: { ...remote.manifest, title: "另一作者的标题" } };
    fireEvent.click(screen.getByRole("button", { name: "保存布局" }));
    await screen.findByRole("button", { name: "编辑布局" });
    expect(screen.queryByRole("textbox", { name: "看板标题" })).toBeNull();
    expect(screen.getByRole("heading", { name: "另一作者的标题" })).toBeTruthy();
    expect(submissions).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "编辑布局" }));
    expect((await screen.findByRole<HTMLInputElement>("textbox", { name: "看板标题" })).value).toBe("另一作者的标题");
  } finally {
    cleanup();
    for (const [key, descriptor] of descriptors) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else Reflect.deleteProperty(globalThis, key);
    }
  }
});
