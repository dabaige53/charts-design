import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import { useVisibleVersionCheck } from "./resource-refresh";

afterEach(cleanup);

// @wu-test type=integration | scope=在线页面版本检查 | protects=页面空闲时持续发送请求或切回页面后未刷新版本
it("checks only when returning to the visible page", async () => {
  const call = mock(async () => ({ dashboardRevision: 2 }));
  const reload = mock(async () => {});
  const setError = mock(() => {});
  renderHook(() => useVisibleVersionCheck({ call, dashboardId: "board", revision: 1, blocked: false, staticMode: false, reload, setError }));
  expect(call).not.toHaveBeenCalled();
  await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
  await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
  expect(call).toHaveBeenCalledTimes(1);
});

// @wu-test type=boundary | scope=在线页面未保存编辑 | protects=切回页面时新版本自动覆盖未保存的编辑
it("warns instead of reloading while editing", async () => {
  const call = mock(async () => ({ dashboardRevision: 2 }));
  const reload = mock(async () => {});
  const setError = mock(() => {});
  renderHook(() => useVisibleVersionCheck({ call, dashboardId: "board", revision: 1, blocked: true, staticMode: false, reload, setError }));
  await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
  expect(reload).not.toHaveBeenCalled();
  expect(setError).toHaveBeenCalledWith("看板已更新，请完成当前操作后重新加载。");
});
