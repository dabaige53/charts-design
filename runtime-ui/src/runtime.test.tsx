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

// @wu-test type=integration | scope=useDashboardRuntime.setFilters | protects=批量应用时同一组件多次查询或收到部分条件，受影响表格未回到首页
it("applies all filter updates in one query per affected component", async () => {
  const call = mock(async (_name: string, args: Config = {}) => patch(args.componentIds[0]));
  const initial = document();
  initial.manifest.filters.push({
    id: "keyword", label: "关键词", field: "region", op: "contains", values: ["旧条件"], componentIds: ["details"],
  });
  const { result } = renderHook(() => useDashboardRuntime(initial, call));
  act(() => {
    result.current.setTable("details", { page: 3, pageSize: 10 });
    result.current.activate("source");
    result.current.activate("total");
    result.current.activate("details");
  });
  await waitFor(() => expect(result.current.loading).toEqual([]));
  call.mockClear();

  act(() => result.current.setFilters(new Map([["region", ["华东"]], ["keyword", []]])));
  await waitFor(() => expect(result.current.loading).toEqual([]));
  const queries = call.mock.calls.map(([, args]) => args!);
  expect(queries.map((args) => args.componentIds[0]).sort()).toEqual(["details", "total"]);
  for (const args of queries) {
    expect(args.filters.map((filter: { values: unknown[] }) => filter.values)).toEqual([["华东"], []]);
    expect(args.tableStates.details.page).toBe(1);
  }
  expect(result.current.document.manifest.filters.map((filter) => filter.values)).toEqual([[], ["旧条件"]]);
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

// @wu-test type=integration | scope=useDashboardRuntime 实时 SQL 刷新 | protects=同版本刷新复用旧值或丢失联动条件及表格页码
it("reloads live data at the same revision with the active linkage and table state", async () => {
  const initial = document();
  initial.manifest.components.source.binding.categoryField = "region";
  initial.manifest.datasets.sales = { mode: "live", fields: { region: { type: "string" } } };
  let value = 100;
  const call = mock(async (name: string, args: Config = {}) => name === "dashboard_refresh"
    ? { document: initial }
    : patch(args.componentIds[0], value));
  const { result } = renderHook(() => useDashboardRuntime(initial, call));
  act(() => { result.current.activate("total"); result.current.activate("details"); });
  await waitFor(() => expect(result.current.loading).toEqual([]));
  act(() => result.current.link({
    id: "runtime-linkage", label: "区域收入", field: "region", op: "in",
    values: ["华东"], componentIds: ["total", "details"],
  }, "source"));
  await waitFor(() => expect(result.current.loading).toEqual([]));
  act(() => result.current.setTable("details", { page: 2, pageSize: 10 }));
  await waitFor(() => expect(result.current.loading).toEqual([]));
  call.mockClear();
  value = 200;

  await act(async () => result.current.reload());

  expect(call.mock.calls[0][0]).toBe("dashboard_refresh");
  await waitFor(() => expect(result.current.document.computed?.components.total.value).toBe(200));
  const reads = call.mock.calls.filter(([name]) => name === "dashboard_view");
  expect(reads).toHaveLength(2);
  for (const [, args] of reads) {
    expect(args?.expectedRevision).toBe(initial.revision);
    expect(args?.filters.at(-1)).toMatchObject({ id: "runtime-linkage", values: ["华东"] });
    expect(args?.tableStates.details.page).toBe(2);
  }
  expect(result.current.view.linkageSource).toBe("source");
});

// @wu-test type=integration | scope=作者工作区保存 | protects=一次保存拆成多次修改往返，或省略检查点和版本校验
it("submits the author edit once and then reads its saved document", async () => {
  const initial = { ...document(), progressive: true };
  const saved = { ...initial, revision: 2 };
  const call = mock(async (name: string) => name === "dashboard_submit"
    ? { ok: true, revision: 2 }
    : { document: saved });
  const { result } = renderHook(() => useDashboardRuntime(initial, call));
  const operations = [{ op: "set_title", value: "Updated" }];

  await act(async () => { expect(await result.current.save(operations)).toBe(true); });

  expect(call.mock.calls.map(([name]) => name)).toEqual(["dashboard_submit", "dashboard_get"]);
  expect(call).toHaveBeenNthCalledWith(1, "dashboard_submit", {
    dashboardId: initial.id, expectedRevision: 1, operations,
  });
  expect(result.current.document.revision).toBe(2);
});

// @wu-test type=boundary | scope=保存检查失败 | protects=检查失败后丢失已写入草稿或重试仍携带过期修订号
it.each(["receipt", "mcp"])("keeps the failed draft revision for repair after %s validation errors", async (transport) => {
  const initial = { ...document(), progressive: true };
  let revision = 1, fail = true;
  const submissions: number[] = [];
  const call = mock(async (name: string, args: Config = {}) => {
    if (name === "dashboard_submit") {
      submissions.push(args.expectedRevision);
      revision++;
      if (fail && transport === "mcp") throw Object.assign(Error("Draft checks failed"), { code: "DOCTOR_FAILED" });
      return { ok: !fail, revision };
    }
    return { document: { ...initial, revision } };
  });
  const { result } = renderHook(() => useDashboardRuntime(initial, call));

  await act(async () => { expect(await result.current.save([])).toBe(false); });
  expect(result.current.document.revision).toBe(2);
  expect(result.current.error).toContain("未通过检查");
  fail = false;
  await act(async () => { expect(await result.current.save([])).toBe(true); });
  expect(submissions).toEqual([1, 2]);
  expect(result.current.document.revision).toBe(3);
});

// @wu-test type=boundary | scope=保存期间版本切换 | protects=迟到的保存读取覆盖新打开的修订
it.each(["success", "error"])("does not replace a newer document or retain recovery after a late save %s", async (outcome) => {
  const initial = { ...document(), progressive: true };
  let complete: ((value: Config) => void) | undefined;
  let reject: ((error: Error) => void) | undefined;
  let reads = 0;
  const call = mock(async (name: string, args: Config = {}) => name === "dashboard_submit"
    ? { ok: true, revision: args.expectedRevision + 1 }
    : reads++ === 0
      ? new Promise<Config>((resolve, fail) => { complete = resolve; reject = fail; })
      : { document: { ...initial, revision: 4 } });
  const { result } = renderHook(() => useDashboardRuntime(initial, call));
  let saving: Promise<boolean>;
  act(() => { saving = result.current.save([]); });
  await waitFor(() => expect(complete).toBeDefined());
  act(() => result.current.accept({ ...initial, revision: 3 }));
  await act(async () => {
    if (outcome === "error") reject!(Error("Late read failure"));
    else complete!({ document: { ...initial, revision: 2 } });
    expect(await saving).toBe(false);
  });
  expect(result.current.document.revision).toBe(3);
  expect(result.current.error).toBe("");
  await act(async () => { expect(await result.current.save([{ op: "set_title", value: "Fresh edit" }])).toBe(true); });
  const submits = call.mock.calls.filter(([name]) => name === "dashboard_submit");
  expect(submits.map(([, args]) => args?.expectedRevision)).toEqual([1, 3]);
  expect(result.current.document.revision).toBe(4);
  expect(result.current.saveRecoveryEpoch).toBe(0);
});

// @wu-test type=boundary | scope=已写入保存的回读恢复 | protects=回读失败后重放已提交修改，或抬高修订号覆盖另一作者的更新
it.each(["saved", "receipt", "mcp"])("reconciles a lost document read after %s before allowing fresh edits", async (outcome) => {
  const initial = { ...document(), progressive: true };
  let remote = initial, readFails = true;
  const submitted: Config[] = [];
  const call = mock(async (name: string, args: Config = {}) => {
    if (name === "dashboard_submit") {
      submitted.push(args);
      remote = { ...remote, revision: remote.revision + 1 };
      if (outcome === "mcp") throw Object.assign(Error("Draft checks failed"), { code: "DOCTOR_FAILED" });
      return { ok: outcome === "saved", revision: remote.revision };
    }
    if (readFails) { readFails = false; throw Error("Temporary read failure"); }
    return { document: remote };
  });
  const { result } = renderHook(() => useDashboardRuntime(initial, call));
  const original = [{ op: "set_title", value: "Original edit" }];
  await act(async () => { expect(await result.current.save(original)).toBe(false); });
  expect(result.current.document.revision).toBe(1);
  expect(result.current.error).toContain("只重新读取最新草稿");

  remote = { ...remote, revision: 3, manifest: { ...remote.manifest, title: "Concurrent author" } };
  const retry = [{ op: "set_title", value: "Stale retry" }];
  await act(async () => { expect(await result.current.save(retry)).toBe(false); });
  expect(submitted).toHaveLength(1);
  expect(call.mock.calls.map(([name]) => name)).toEqual(["dashboard_submit", "dashboard_get", "dashboard_get"]);
  expect(result.current.document.revision).toBe(3);
  expect(result.current.document.manifest.title).toBe("Concurrent author");
  expect(result.current.saveRecoveryEpoch).toBe(1);
  expect(result.current.error).toContain("核对内容后重新进入编辑");

  // Only a later explicit edit may submit against the freshly reviewed version.
  const fresh = [{ op: "set_title", value: "Reviewed edit" }];
  await act(async () => { await result.current.save(fresh); });
  expect(submitted).toHaveLength(2);
  expect(submitted[1]).toMatchObject({ expectedRevision: 3, operations: fresh });
});

// @wu-test type=boundary | scope=保存明确拒绝 | protects=普通版本冲突或无效操作被当作已持久化保存并清空当前编辑
it.each(["REVISION_CONFLICT", "INVALID_OPERATION"])("preserves the normal editor retry path after %s", async (code) => {
  const initial = { ...document(), progressive: true };
  const call = mock(async () => { throw Object.assign(Error("Explicit rejection"), { code }); });
  const { result } = renderHook(() => useDashboardRuntime(initial, call));
  await act(async () => { await result.current.save([]); });
  await act(async () => { await result.current.save([]); });
  expect(call.mock.calls).toHaveLength(2);
  expect(result.current.document).toBe(initial);
  expect(result.current.saveRecoveryEpoch).toBe(0);
  expect(result.current.error).toBe("Error: Explicit rejection");
});
