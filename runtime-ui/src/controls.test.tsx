import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, mock } from "bun:test";
import { ActiveFilters, MultiSelect } from "./controls";

const originalResizeObserver = globalThis.ResizeObserver;
const originalScrollIntoView = HTMLElement.prototype.scrollIntoView;
const originalElement = globalThis.Element;
const originalCustomEvent = globalThis.CustomEvent;
const originalNodeFilter = globalThis.NodeFilter;
beforeEach(() => {
  // jsdom 不实现下拉列表依赖的布局观察和滚动 API。
  globalThis.Element = window.Element;
  globalThis.CustomEvent = window.CustomEvent;
  globalThis.NodeFilter = window.NodeFilter;
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  HTMLElement.prototype.scrollIntoView = () => {};
});
afterEach(() => {
  cleanup();
  globalThis.ResizeObserver = originalResizeObserver;
  HTMLElement.prototype.scrollIntoView = originalScrollIntoView;
  globalThis.Element = originalElement;
  globalThis.CustomEvent = originalCustomEvent;
  globalThis.NodeFilter = originalNodeFilter;
});

// @wu-test type=performance | scope=MultiSelect option loading | protects=打开筛选器立即加载选项且关闭时不预取
it("loads options immediately when opened without prefetching closed menus", async () => {
  const loadOptions = mock(async () => ({
    options: [{ value: "east", label: "华东" }], hasMore: false,
  }));
  render(<MultiSelect label="区域" options={[]} value={[]} onChange={() => {}}
    loadOptions={loadOptions} />);
  expect(loadOptions).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("combobox"));
  expect(loadOptions).toHaveBeenCalledWith("", 0);
  expect(await screen.findByRole("option", { name: "华东" })).toBeTruthy();
});

// @wu-test type=regression | scope=required selection controls | protects=防止 required-month-20261112 复发：必选月份允许清空或全选且已有空值显示全部
it("disables clearing a required single choice while allowing selection from empty", async () => {
  const change = mock(() => {});
  const options = [
    { value: "2026-10", label: "2026-10" },
    { value: "2026-09", label: "2026-09" },
  ];
  const { rerender } = render(<MultiSelect label="月份" required single
    options={options} value={["2026-10"]} onChange={change} />);
  const trigger = screen.getByRole("combobox");
  fireEvent.click(trigger);
  const clear = await screen.findByRole("button", { name: "清空" }) as HTMLButtonElement;
  expect(clear.disabled).toBe(true);
  fireEvent.click(clear);
  expect(change).not.toHaveBeenCalled();
  fireEvent.click(trigger);
  rerender(<MultiSelect label="月份" required single options={options}
    value={[]} onChange={change} />);
  expect(screen.getByText("请选择")).toBeTruthy();
  expect(screen.queryByText("全部")).toBeNull();
  fireEvent.click(trigger);
  expect((await screen.findByRole("button", { name: "清空" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByRole("button", { name: "全选" })).toBeNull();
  fireEvent.click(screen.getByRole("option", { name: "2026-10" }));
  expect(change).toHaveBeenCalledWith(["2026-10"]);
});

// @wu-test type=regression | scope=ActiveFilters required selection | protects=防止 required-month-20261112 复发：必选月份被生效条件标签的移除按钮清空
it("keeps required condition badges while optional conditions remain removable", () => {
  const remove = mock(() => {});
  render(<ActiveFilters items={[
    { id: "period", label: "月份：2026-10", removable: false },
    { id: "region", label: "区域：华东" },
  ]} onRemove={remove} onClear={() => {}} showClear={false} />);
  expect(screen.getByText("月份：2026-10")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "移除月份：2026-10" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "移除区域：华东" }));
  expect(remove).toHaveBeenCalledWith("region");
});
