import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import { TooltipProvider } from "./components/ui/tooltip";
import { PositionComments, scrollToComment } from "./position-comments";
import type { Config, Document } from "./types";

afterEach(cleanup);

// @wu-test type=behavior | scope=批注列表定位 | protects=长图表只滚到图表中心而未显示顶部批注编号
it("scrolls to the annotation marker instead of the center of its large target", () => {
  const root = document.createElement("div");
  root.getBoundingClientRect = () => ({ x: 0, y: 1000, left: 0, top: 1000, right: 500, bottom: 3000, width: 500, height: 2000, toJSON() {} });
  document.body.appendChild(root);
  const original = window.scrollBy;
  const scroll = mock(() => {});
  window.scrollBy = scroll;
  try {
    scrollToComment(root, { componentId: null, anchor: { scope: "page", kind: "area", quote: "", rect: { x: 0, y: 0.1, width: 1, height: 0.8 } } });
    expect(scroll).toHaveBeenCalledWith({ top: 1200 - 12 - window.innerHeight / 2, behavior: "auto" });
  } finally {
    window.scrollBy = original;
    root.remove();
  }
});

// @wu-test type=integration | scope=PositionComments 状态切换和定位 | protects=已解决批注计入未解决数量或重新打开后编号被面板遮挡
it.each([false, true])("updates status without losing the marker (project=%s)", async (progressive) => {
  const previous = {
    Element: globalThis.Element, ResizeObserver: globalThis.ResizeObserver,
    location: globalThis.location, sessionStorage: globalThis.sessionStorage,
  };
  const previousScrollBy = window.scrollBy;
  const previousWidth = window.innerWidth;
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 640 });
  window.scrollBy = () => {};
  Object.assign(globalThis, {
    Element: window.Element, location: window.location, sessionStorage: window.sessionStorage,
    ResizeObserver: class { observe() {} disconnect() {} },
  });
  const root = document.createElement("div");
  root.getBoundingClientRect = () => ({ x: 20, y: 100, left: 20, top: 100, right: 520, bottom: 600, width: 500, height: 500, toJSON() {} });
  document.body.appendChild(root);
  let notes: Config[] = [{ id: "note-1", componentId: null, text: "修改图表",
    anchor: { scope: "page", kind: "area", quote: "", rect: { x: 0.412, y: 0, width: 0.2, height: 0.2 } } }];
  const doc: Document = { id: "board", revision: 1, progressive, snapshot: { datasets: {} },
    manifest: { title: "Comments", annotations: notes, components: {}, filters: [],
      layout: {}, metrics: {}, datasets: {} } };
  let uncertainReply: Config | undefined;
  const call = mock(async (name: string, args?: Config) => {
    if (name === "dashboard_annotations") return { annotations: notes, revision: 1 };
    if (name === "dashboard_patch") {
      notes = args!.operations[0].value;
      return { document: { manifest: { annotations: notes } } };
    }
    if (name === "dashboard_annotation_apply") {
      const command = args!.command;
      if (command.action === "reply") {
        if (!uncertainReply) {
          uncertainReply = structuredClone(command);
          throw Error("响应中断，输入已保留");
        }
        expect(command).toEqual(uncertainReply);
        notes = notes.map((note) => ({ ...note, replies: [command.value] }));
      } else {
        expect(command.action).toBe("status");
        notes = notes.map((note) => ({ ...note, status: command.status }));
      }
      return { annotations: notes, annotationChange: 1 };
    }
    throw Error(`Unexpected call: ${name}`);
  });
  try {
    render(<TooltipProvider><PositionComments document={doc} root={{ current: root }} active
      onActiveChange={() => {}} onActivityChange={() => {}} call={call} readOnly={false}
      filters={[]} onNotesChange={() => {}} /></TooltipProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "打开批注 1：修改图表" }));
    expect(screen.getByRole("button", { name: "批注列表（1）" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "标记已解决" }));
    await screen.findByRole("button", { name: "重新打开" });
    expect(screen.getByRole("button", { name: "批注列表" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "收起批注面板" }));
    expect(screen.queryByRole("button", { name: "打开批注 1：修改图表" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "批注列表" }));
    fireEvent.click(screen.getByRole("button", { name: "已解决" }));
    fireEvent.click(screen.getByRole("button", { name: /修改图表/ }));
    fireEvent.click(screen.getByRole("button", { name: "重新打开" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "批注列表（1）" })).toBeTruthy());
    const marker = await screen.findByRole("button", { name: "打开批注 1：修改图表" });
    const panel = screen.getByRole("dialog");
    const markerLeft = parseFloat(marker.style.left);
    const panelLeft = parseFloat(panel.style.left);
    const panelWidth = parseFloat(panel.style.width);
    expect(panelLeft >= markerLeft + 32 || panelLeft + panelWidth <= markerLeft).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "收起批注面板" }));
    expect(await screen.findByRole("button", { name: "打开批注 1：修改图表" })).toBeTruthy();
    if (progressive) {
      fireEvent.click(screen.getByRole("button", { name: "打开批注 1：修改图表" }));
      fireEvent.change(screen.getByLabelText("回复"), { target: { value: "保留并重试" } });
      fireEvent.click(screen.getByRole("button", { name: "提交回复" }));
      await screen.findByText("响应中断，输入已保留");
      expect((screen.getByLabelText("回复") as HTMLTextAreaElement).value).toBe("保留并重试");
      fireEvent.click(screen.getByRole("button", { name: "提交回复" }));
      await screen.findByText("回复 1");
      expect(call.mock.calls.filter(([name]) => name === "dashboard_annotations")).toHaveLength(1);
      expect(call.mock.calls.filter(([name]) => name === "dashboard_patch")).toHaveLength(0);
    }
  } finally {
    cleanup();
    root.remove();
    window.scrollBy = previousScrollBy;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: previousWidth });
    Object.assign(globalThis, previous);
  }
});

