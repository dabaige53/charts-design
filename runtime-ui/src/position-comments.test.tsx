import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import { TooltipProvider } from "./components/ui/tooltip";
import { PositionComments } from "./position-comments";
import type { Config, Document } from "./types";

afterEach(cleanup);

// @wu-test type=integration | scope=PositionComments 旧批注定位 | protects=无引文且无坐标的旧批注使批注列表和正常标记停止渲染
it("keeps an unpositioned comment readable without hiding valid markers", async () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "ResizeObserver");
  Object.defineProperty(globalThis, "ResizeObserver", { configurable: true, value: class { observe() {} disconnect() {} } });
  const page = document.createElement("div");
  document.body.append(page);
  page.getBoundingClientRect = () => new window.DOMRect(0, 0, 100, 100);
  try {
    const doc: Document = { id: "board", revision: 2, progressive: true,
      manifest: { title: "Board", components: {}, filters: [], layout: {}, metrics: {}, datasets: {} },
      snapshot: { datasets: {} } };
    const old = { id: "old", componentId: null, text: "Missing position", anchor: { scope: "page", kind: "element" } };
    const placed = { ...old, id: "valid", text: "With position",
      anchor: { scope: "page", kind: "area", rect: { x: 0, y: 0, width: 0.5, height: 0.5 } } };
    const call = mock(async () => ({ revision: 2, annotations: [old, placed], independentSave: true }));
    render(<TooltipProvider><PositionComments document={doc} root={{ current: page }} active onActiveChange={() => {}}
      onActivityChange={() => {}} call={call} readOnly={false} filters={[]} projectRoot="sample" onNotesChange={() => {}} /></TooltipProvider>);
    await screen.findByRole("button", { name: /打开批注.*With position/ });
    expect(screen.queryByRole("button", { name: /打开批注.*Missing position/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "批注列表（2）" }));
    expect(screen.getByRole("button", { name: /Missing position/ })).toBeTruthy();
  } finally {
    cleanup();
    page.remove();
    if (original) Object.defineProperty(globalThis, "ResizeObserver", original);
    else Reflect.deleteProperty(globalThis, "ResizeObserver");
  }
});

// @wu-test type=integration | scope=PositionComments | protects=保存时重复读取批注或调用整页修改
it("uses the loaded revision and sends one request when resolving a comment", async () => {
  const note = { id: "note", componentId: null, text: "Review sample", createdAt: "2026-11-25" };
  const doc: Document = { id: "board", revision: 2, progressive: true,
    manifest: { title: "Board", components: {}, filters: [], layout: {}, metrics: {}, datasets: {} },
    snapshot: { datasets: {} } };
  const call = mock(async (name: string, args?: Config) => {
    if (name === "dashboard_annotations") return { revision: 3, annotations: [note], independentSave: true };
    if (name === "dashboard_annotations_update") return { revision: 3, annotations: args?.annotations };
    throw Error(`Unexpected call ${name}`);
  });
  const changed = mock(() => {});
  render(<TooltipProvider><PositionComments document={doc} root={{ current: null }} active onActiveChange={() => {}}
    onActivityChange={() => {}} call={call} readOnly={false} filters={[]} projectRoot="sample" onNotesChange={changed} /></TooltipProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "批注列表（1）" }));
  fireEvent.click(await screen.findByRole("button", { name: /Review sample/ }));
  fireEvent.click(await screen.findByRole("button", { name: "标记已解决" }));
  await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
  expect(call.mock.calls).toEqual([
    ["dashboard_annotations", { dashboardId: "board", includeTargets: false }],
    ["dashboard_annotations_update", { dashboardId: "board", expectedRevision: 3, expectedAnnotations: [note],
      annotations: [{ ...note, status: "resolved" }] }],
  ]);
});

// @wu-test type=integration | scope=PositionComments 提交批注 | protects=慢读取和第一条保存阻塞第二条，或失败重试丢失批注
it("starts successive appends before the list or the first save finishes and preserves retries", async () => {
  const globals = ["sessionStorage", "ResizeObserver", "Element"] as const;
  const originals = globals.map((name) => Object.getOwnPropertyDescriptor(globalThis, name));
  const key = 'charts-position-draft:["sample","board",false]';
  const draft = { id: "new-note", componentId: null, text: "Keep my draft",
    anchor: { scope: "page", kind: "area", quote: "", rect: { x: 0, y: 0, width: 0.5, height: 0.5 } } };
  const page = document.createElement("div");
  Object.defineProperty(globalThis, "sessionStorage", { configurable: true, value: window.sessionStorage });
  Object.defineProperty(globalThis, "ResizeObserver", { configurable: true, value: class { observe() {} disconnect() {} } });
  Object.defineProperty(globalThis, "Element", { configurable: true, value: window.Element });
  window.sessionStorage.setItem(key, JSON.stringify({ draft, replies: {} }));
  try {
    const doc: Document = { id: "board", revision: 2, progressive: true,
      manifest: { title: "Board", components: {}, filters: [], layout: {}, metrics: {}, datasets: {}, annotations: [] },
      snapshot: { datasets: {} } };
    let finishRead!: (result: Config) => void;
    let rejectFirst!: (reason: Error) => void;
    let finishSecond!: (result: Config) => void;
    const reading = new Promise<Config>((resolve) => { finishRead = resolve; });
    const first = new Promise<Config>((_, reject) => { rejectFirst = reject; });
    const second = new Promise<Config>((resolve) => { finishSecond = resolve; });
    let saves = 0;
    const call = mock(async (name: string, args?: Config) => {
      if (name === "dashboard_annotations") return reading;
      if (name === "dashboard_annotations_update") {
        saves++;
        if (saves === 1) return first;
        if (saves === 2) return second;
        return { revision: 3, annotation: args?.append };
      }
      throw Error(`Unexpected call ${name}`);
    });
    document.body.append(page);
    page.getBoundingClientRect = () => new window.DOMRect(0, 0, 100, 100);
    render(<TooltipProvider><PositionComments document={doc} root={{ current: page }} active onActiveChange={() => {}}
      onActivityChange={() => {}} call={call} readOnly={false} filters={[]} projectRoot="sample" onNotesChange={() => {}} /></TooltipProvider>);
    const submit = await screen.findByRole("button", { name: "提交批注" }) as HTMLButtonElement;
    await waitFor(() => expect(submit.disabled).toBe(false));
    fireEvent.click(submit);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByText("正在保存 1 条批注…")).toBeTruthy();
    expect(call.mock.calls.map(([name]) => name)).toEqual(["dashboard_annotations", "dashboard_annotations_update"]);
    const firstArgs = call.mock.calls[1][1];
    expect(firstArgs).toEqual({ dashboardId: "board", append: expect.objectContaining({ id: draft.id, text: draft.text }) });
    expect(JSON.parse(window.sessionStorage.getItem(key) || "{}").submissions[0].text).toBe(draft.text);
    fireEvent.keyDown(page, { key: "Enter" });
    fireEvent.change(await screen.findByRole("textbox", { name: "批注内容" }), { target: { value: "Second annotation" } });
    const submitSecond = screen.getByRole("button", { name: "提交批注" }) as HTMLButtonElement;
    await waitFor(() => expect(submitSecond.disabled).toBe(false));
    fireEvent.click(submitSecond);
    const secondNote = call.mock.calls[2][1]?.append;
    expect(secondNote.text).toBe("Second annotation");
    expect(secondNote.id).not.toBe(draft.id);
    await act(async () => {
      finishSecond({ revision: 3, annotation: secondNote });
      finishRead({ revision: 3, annotations: [], independentSave: true });
      rejectFirst(Error("Network unavailable"));
    });
    expect(screen.getByRole("button", { name: "批注列表（1）" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重试未保存的批注" }));
    expect(call.mock.calls[3][1]).toEqual(firstArgs);
    await screen.findByRole("button", { name: "批注列表（2）" });
  } finally {
    cleanup();
    page.remove();
    window.sessionStorage.removeItem(key);
    globals.forEach((name, index) => {
      const descriptor = originals[index];
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else Reflect.deleteProperty(globalThis, name);
    });
  }
});
