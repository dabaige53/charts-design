import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import { FilterParameters } from "./filter-parameters";
import type { Document, Filter } from "./types";

Object.defineProperty(globalThis, "CustomEvent", { configurable: true, value: window.CustomEvent });
Object.defineProperty(globalThis, "NodeFilter", { configurable: true, value: window.NodeFilter });

const filters: Filter[] = [
  { id: "region", label: "区域", field: "region", op: "in", values: ["华东"], componentIds: ["sales"] },
  { id: "amount", label: "金额", field: "amount", op: "range", values: [0, 200], componentIds: ["sales"] },
  { id: "keyword", label: "关键词", field: "region", op: "contains", values: [], componentIds: ["sales"] },
];
const doc: Document = {
  id: "sales", revision: 1,
  manifest: {
    title: "销售",
    components: { sales: { kind: "table", title: "销售", datasetId: "sales" } },
    datasets: { sales: { fields: { region: { type: "string" }, amount: { type: "number" } } } },
    filters, layout: {}, metrics: {},
  },
  snapshot: { datasets: {} },
};
const clipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");
afterEach(() => {
  cleanup();
  if (clipboard) Object.defineProperty(navigator, "clipboard", clipboard);
  else Reflect.deleteProperty(navigator, "clipboard");
});

// @wu-test type=behavior | scope=FilterParameters 复制和应用 | protects=复制结果无法恢复条件、保留了未列出的旧条件或提示的条件数错误
it("copies active conditions and applies them to replace the current selection", async () => {
  const writeText = mock(async (_text: string) => {});
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  const onApply = mock();
  const { rerender } = render(<FilterParameters document={doc} filters={filters} onApply={onApply} />);
  fireEvent.click(screen.getByRole("button", { name: "复制筛选条件" }));
  await screen.findByText("已复制，稍后可粘贴恢复。");
  const text = writeText.mock.calls[0][0];
  expect(JSON.parse(text)).toEqual({ region: ["华东"], amount: [0, 200] });

  rerender(<FilterParameters document={doc} filters={filters.map((filter) =>
    filter.id === "keyword" ? { ...filter, values: ["旧条件"] } : filter
  )} onApply={onApply} />);
  fireEvent.click(screen.getByRole("button", { name: "粘贴筛选条件" }));
  fireEvent.change(screen.getByRole("textbox", { name: "已复制的筛选条件" }), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "应用筛选" }));
  expect(onApply).toHaveBeenCalledWith(new Map<string, (number | string)[]>([
    ["region", ["华东"]], ["amount", [0, 200]], ["keyword", []],
  ]));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(screen.getByRole("status").textContent).toBe("已应用 2 项筛选条件。");
});

// @wu-test type=behavior | scope=FilterParameters 空筛选反馈 | protects=粘贴空筛选时把无变化误报为清除成功，或不说明已清除旧条件
it.each([
  [true, "已清除此栏的筛选条件。"],
  [false, "此栏没有需要清除的条件。"],
] as const)("reports the outcome of an empty selection when existing conditions were present: %s", (hadSelection, message) => {
  render(<FilterParameters document={doc} filters={hadSelection ? filters : filters.map((filter) => ({ ...filter, values: [] }))} onApply={mock()} />);
  fireEvent.click(screen.getByRole("button", { name: "粘贴筛选条件" }));
  fireEvent.change(screen.getByRole("textbox", { name: "已复制的筛选条件" }), { target: { value: "{}" } });
  fireEvent.click(screen.getByRole("button", { name: "应用筛选" }));
  expect(screen.getByRole("status").textContent).toBe(message);
});

// @wu-test type=boundary | scope=FilterParameters 输入校验 | protects=无效 JSON、非本栏条件或错误类型部分覆盖当前筛选
it("rejects malformed JSON and incompatible filters without applying any condition", () => {
  const onApply = mock();
  render(<FilterParameters document={doc} filters={filters} onApply={onApply} />);
  fireEvent.click(screen.getByRole("button", { name: "粘贴筛选条件" }));
  for (const [value, error] of [
    ['{"region":', "请重新复制筛选条件，再完整粘贴"],
    ['{"region":["华南"],"other":[1]}', "请从同一个筛选栏复制条件"],
    ['{"region":["华南"],"amount":["0",200]}', "「金额」的值格式不对"],
  ]) {
    fireEvent.change(screen.getByRole("textbox", { name: "已复制的筛选条件" }), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "应用筛选" }));
    expect(screen.getByRole("alert").textContent).toContain(error);
    expect(onApply).not.toHaveBeenCalled();
  }
});

// @wu-test type=behavior | scope=FilterParameters 手动复制 | protects=宿主拒绝剪贴板写入时无法获得筛选 JSON
it("offers selectable JSON when the clipboard rejects writes", async () => {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true, value: { writeText: mock(async () => { throw Error("denied"); }) },
  });
  render(<FilterParameters document={doc} filters={filters} onApply={mock()} />);
  fireEvent.click(screen.getByRole("button", { name: "复制筛选条件" }));
  const input = await screen.findByRole<HTMLTextAreaElement>("textbox", { name: "要复制的内容" });
  expect(input.readOnly).toBe(true);
  expect(JSON.parse(input.value)).toEqual({ region: ["华东"], amount: [0, 200] });
});
