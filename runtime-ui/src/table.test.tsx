import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import { DataTable } from "./table";
import { TooltipProvider } from "./components/ui/tooltip";

afterEach(cleanup);

// @wu-test type=behavior | scope=DataTable | protects=筛选和翻页加载时表头与已显示的数据被重新移除
it("keeps existing table content mounted while state and data update", () => {
  Object.defineProperty(globalThis, "DocumentFragment", { configurable: true, value: window.DocumentFragment });
  Object.defineProperty(globalThis, "HTMLFormElement", { configurable: true, value: window.HTMLFormElement });
  Object.defineProperty(window, "matchMedia", { configurable: true, value: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }) });
  const onChange = mock(() => {});
  const config = { columns: [{ key: "name", title: "名称" }], rows: [{ name: "华东" }] };
  const { rerender } = render(<TooltipProvider><DataTable config={config} state={{ page: 1, pageSize: 10 }} onChange={onChange} /></TooltipProvider>);
  const header = screen.getByText("名称");
  const value = screen.getByText("华东").firstChild;
  rerender(<TooltipProvider><DataTable config={config} state={{ page: 2, pageSize: 10 }} onChange={onChange} loading /></TooltipProvider>);
  expect(screen.getByText("名称") === header).toBe(true);
  expect(screen.getByText("华东").firstChild === value).toBe(true);
  rerender(<TooltipProvider><DataTable config={{ ...config, columns: [...config.columns], rows: [{ name: "华南" }] }} state={{ page: 2, pageSize: 10 }} onChange={onChange} /></TooltipProvider>);
  expect(screen.getByText("名称") === header).toBe(true);
  expect(screen.getByText("华南")).toBeTruthy();
  fireEvent.click(header.closest("button")!);
  expect(onChange).toHaveBeenCalled();
});
