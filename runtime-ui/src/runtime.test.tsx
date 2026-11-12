import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import { useDashboardRuntime } from "./runtime";
import type { Config, Document } from "./types";

afterEach(cleanup);

function document(): Document {
  return {
    id: "runtime-interaction",
    revision: 1,
    manifest: {
      title: "Runtime interaction",
      components: {
        source: { kind: "legacy", family: "chart", title: "区域收入", binding: { datasetId: "sales" } },
        total: { kind: "legacy", family: "kpi", title: "收入", binding: { datasetId: "sales" } },
        details: { kind: "table", title: "明细", datasetId: "sales" },
      },
      filters: [{ id: "region", label: "区域", field: "region", op: "in", values: [], componentIds: ["total", "details"] }],
      layout: {}, metrics: {}, datasets: {},
    },
    snapshot: { datasets: {} },
    computed: { components: { total: { value: 11 } }, tables: {} },
  };
}

function patch(id: string, value = 100): Config {
  return { id: "runtime-interaction", revision: 1, computed: { components: { [id]: { value } } } };
}

// @wu-test type=regression | scope=useDashboardRuntime required filters | protects=防止 required-month-20261112 复发：必选单月被清空或多选且重置全部丢失月份
it("retains the required single month when clearing, resetting or attempting multiple months", () => {
  const initial = document();
  initial.manifest.filters.push({
    id: "period", label: "月份", field: "month", op: "in", required: true,
    selectionMode: "single", values: ["2026-10"], componentIds: ["total"],
  });
  const call = mock(async () => ({}));
  const { result } = renderHook(() => useDashboardRuntime(initial, call));
  act(() => result.current.setFilter("region", ["华东"]));
  act(() => result.current.setFilter("period", []));
  act(() => result.current.setFilter("period", ["2026-09", "2026-10"]));
  expect(result.current.view.filters.find(f => f.id === "period")!.values).toEqual(["2026-10"]);
  act(() => result.current.clear());
  expect(result.current.view.filters.find(f => f.id === "region")!.values).toEqual([]);
  expect(result.current.view.filters.find(f => f.id === "period")!.values).toEqual(["2026-10"]);
  act(() => result.current.setFilter("period", ["2026-09"]));
  expect(result.current.view.filters.find(f => f.id === "period")!.values).toEqual(["2026-09"]);
});

// @wu-test type=regression | scope=useDashboardRuntime required filter recovery | protects=防止 required-month-20261112 复发：已有空月份状态无法重新选择月份恢复
it("accepts a month selection when a required filter starts empty", () => {
  const initial = document();
  initial.manifest.filters[0] = {
    id: "period", label: "月份", field: "month", op: "in", required: true,
    selectionMode: "single", values: [], componentIds: ["total"],
  };
  const call = mock(async () => ({}));
  const { result } = renderHook(() => useDashboardRuntime(initial, call));
  act(() => result.current.setFilter("period", ["2026-10"]));
  expect(result.current.view.filters[0].values).toEqual(["2026-10"]);
});

// @wu-test type=integration | scope=useDashboardRuntime.setFilter | protects=局部筛选重新查询未关联图表或清空已显示数值
it("updates only filter consumers and retains the displayed value while waiting", async () => {
  let complete: ((result: Config) => void) | undefined;
  const call = mock(async (_name: string, args: Config = {}) => {
    if (args.filters[0].values.length) return new Promise<Config>((resolve) => { complete = resolve; });
    return patch(args.componentIds[0]);
  });
  const initial = document();
  const { result } = renderHook(() => useDashboardRuntime(initial, call));
  act(() => { result.current.activate("source"); result.current.activate("total"); });
  await waitFor(() => expect(result.current.loading).toEqual([]));
  call.mockClear();
  act(() => result.current.setFilter("region", ["华东"]));
  await waitFor(() => expect(call).toHaveBeenCalledTimes(1));
  expect(call.mock.calls[0][1]!.componentIds).toEqual(["total"]);
  expect(result.current.document.computed?.components.total.value).toBe(100);
  await act(async () => { complete!(patch("total", 200)); });
  expect(result.current.document.computed?.components.total.value).toBe(200);
});

// @wu-test type=integration | scope=useDashboardRuntime.request | protects=快速筛选时旧查询覆盖新结果或提前清除加载状态
it("discards an older response that finishes after the newest selection", async () => {
  const responses: ((result: Config) => void)[] = [];
  const call = mock(() => new Promise<Config>((resolve) => { responses.push(resolve); }));
  const initial = document();
  const { result } = renderHook(() => useDashboardRuntime(initial, call));
  act(() => result.current.activate("total"));
  await waitFor(() => expect(call).toHaveBeenCalledTimes(1));
  act(() => result.current.setFilter("region", ["华东"]));
  await waitFor(() => expect(call).toHaveBeenCalledTimes(2));
  await act(async () => { responses[1](patch("total", 200)); });
  await act(async () => { responses[0](patch("total", 100)); });
  expect(result.current.document.computed?.components.total.value).toBe(200);
  expect(result.current.loading).toEqual([]);
});

// @wu-test type=integration | scope=useDashboardRuntime.setTable | protects=表格翻页导致全部指标和图表重复查询
it("queries only the table when its page changes", async () => {
  const call = mock(async (_name: string, args: Config = {}) => patch(args.componentIds[0]));
  const initial = document();
  const { result } = renderHook(() => useDashboardRuntime(initial, call));
  act(() => { result.current.activate("source"); result.current.activate("total"); result.current.activate("details"); });
  await waitFor(() => expect(result.current.loading).toEqual([]));
  call.mockClear();
  act(() => result.current.setTable("details", { page: 2, pageSize: 10 }));
  await waitFor(() => expect(result.current.loading).toEqual([]));
  expect(call).toHaveBeenCalledTimes(1);
  expect(call.mock.calls[0][1]!.componentIds).toEqual(["details"]);
  expect(call.mock.calls[0][1]!.tableStates.details.page).toBe(2);
});

// @wu-test type=regression | scope=useDashboardRuntime table response | protects=防止 audit-6 复发：分页返回覆盖等待期间修改的列顺序和显隐
it("preserves newer column settings when a pending page response arrives", async () => {
  let complete: ((value: Config) => void) | undefined;
  const call = mock(async (_name: string, args: Config = {}) => {
    if (args.tableStates.details.page === 2) {
      return new Promise<Config>(resolve => { complete = resolve; });
    }
    return patch("details");
  });
  const initial = document();
  const { result } = renderHook(() => useDashboardRuntime(initial, call));
  act(() => result.current.activate("details"));
  await waitFor(() => expect(result.current.loading).toEqual([]));
  act(() => result.current.setTable("details", {
    page: 2, pageSize: 10, columns: ["a", "b"], visible: ["a", "b"],
  }));
  await waitFor(() => expect(complete).toBeDefined());
  act(() => result.current.setTable("details", {
    page: 2, pageSize: 10, columns: ["b", "a"], visible: ["b"],
  }));
  await act(async () => complete!({
    ...patch("details"), computed: { tables: { details: {
      page: 2, pageSize: 10, totalRows: 30, columns: ["a", "b"], visible: ["a", "b"],
    } } },
  }));
  expect(result.current.view.tables.details).toMatchObject({
    page: 2, totalRows: 30, columns: ["b", "a"], visible: ["b"],
  });
  expect(call).toHaveBeenCalledTimes(2);
});

// @wu-test type=integration | scope=useDashboardRuntime.link | protects=柱图联动把来源图本身过滤成单根柱子或刷新无关组件
it("preserves the source chart when applying linkage to other components", async () => {
  const call = mock(async (_name: string, args: Config = {}) => patch(args.componentIds[0]));
  const initial = document();
  const { result } = renderHook(() => useDashboardRuntime(initial, call));
  act(() => { result.current.activate("source"); result.current.activate("total"); result.current.activate("details"); });
  await waitFor(() => expect(result.current.loading).toEqual([]));
  call.mockClear();
  act(() => result.current.link({
    id: "runtime-linkage", label: "区域收入", field: "region", op: "in", values: ["华东"], componentIds: ["total", "details"],
  }, "source"));
  await waitFor(() => expect(result.current.loading).toEqual([]));
  expect(call.mock.calls.map(([, args]) => args!.componentIds[0]).sort()).toEqual(["details", "total"]);
  expect(result.current.view.linkageSource).toBe("source");
  expect(result.current.document.computed?.components.source.value).toBe(100);
});
