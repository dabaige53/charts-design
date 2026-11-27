import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import { StaticSite } from "./static";
import { TooltipProvider } from "./components/ui/tooltip";
import type { Document } from "./types";

const originalFetch = globalThis.fetch;
const originalLocation = Object.getOwnPropertyDescriptor(globalThis, "location");
afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  if (originalLocation) Object.defineProperty(globalThis, "location", originalLocation);
  else Reflect.deleteProperty(globalThis, "location");
});

// @wu-test type=integration | scope=静态分享筛选常显配置 | protects=固定分享页忽略第四项常显配置或将高级筛选移到主栏
it("uses saved filter visibility in a published report", async () => {
  Object.defineProperty(globalThis, "location", { configurable: true, value: new URL("https://charts.example/s/share/") });
  const doc: Document = {
    id: "report", revision: 1,
    manifest: { title: "筛选配置报告", viewMode: "filtered-report", report: { markdown: "" },
      components: {}, layout: {}, metrics: {}, datasets: {},
      filters: ["月份", "基地", "机型", "航线", "渠道"].map((label, index) => ({
        id: `choice-${index}`, label, field: "field", op: "contains", values: [],
        componentIds: [], alwaysVisible: index < 4,
      })) },
    snapshot: { datasets: {} },
  };
  globalThis.fetch = (async () => Response.json(doc)) as unknown as typeof fetch;
  render(<TooltipProvider><StaticSite /></TooltipProvider>);
  await screen.findByRole("heading", { name: "筛选配置报告" });
  expect(screen.getByPlaceholderText("航线").closest("[inert]")).toBeNull();
  expect(screen.getByPlaceholderText("渠道").closest("[inert]")).not.toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "更多筛选" }));
  expect(screen.getByPlaceholderText("渠道").closest("[inert]")).toBeNull();
});

// @wu-test type=integration | scope=StaticSite 页面切换和权限 | protects=多页面分享误加载未选页面、无批注后端的ZIP显示可提交入口
it("loads selected pages from the shared site", async () => {
  Object.defineProperty(globalThis, "location", { configurable: true, value: new URL("https://charts.example/s/share/") });
  const pages = [
    { id: "first", title: "第一页", path: "document.json" },
    { id: "second", title: "第二页", path: "pages/second/document.json" },
  ];
  const documents = Object.fromEntries(pages.map(({ id, path, title }) => {
    const doc: Document = {
      id, revision: 1, staticPages: pages,
      manifest: { title, viewMode: "filtered-report", report: { markdown: "" },
        components: {}, filters: [], layout: {}, metrics: {}, datasets: {} },
      snapshot: { datasets: {} },
    };
    return [new URL(path, location.href).href, doc];
  }));
  const fetchMock = mock(async (url: RequestInfo | URL) => Response.json(documents[String(url)]));
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  render(<StaticSite />);
  await screen.findByRole("heading", { name: "第一页" });
  expect(screen.queryByRole("button", { name: "添加位置批注" })).toBeNull();
  expect(screen.queryByRole("button", { name: "查看批注" })).toBeNull();
  const select = await screen.findByRole("combobox", { name: "切换看板" });
  fireEvent.keyDown(select, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name: "第二页" }));
  await screen.findByRole("heading", { name: "第二页" });
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

// @wu-test type=integration | scope=独立分享批注 | protects=只读内容禁止位置批注、写批注重载整页数据、刷新无法读取原分享版本的段落批注
it("adds and reloads a report annotation through the share service while content stays read-only", async () => {
  const keys = ["sessionStorage", "ResizeObserver", "CSS"] as const;
  const descriptors = keys.map(key => Object.getOwnPropertyDescriptor(globalThis, key));
  const originalRect = window.HTMLElement.prototype.getBoundingClientRect;
  Object.defineProperty(globalThis, "location", { configurable: true, value: new URL("https://charts.example/s/one/") });
  Object.defineProperty(globalThis, "sessionStorage", { configurable: true, value: window.sessionStorage });
  Object.defineProperty(globalThis, "ResizeObserver", { configurable: true, value: class { observe() {} disconnect() {} } });
  Object.defineProperty(globalThis, "CSS", { configurable: true, value: { escape: (value: string) => value } });
  window.HTMLElement.prototype.getBoundingClientRect = () => new window.DOMRect(20, 40, 600, 300);
  const notes: Record<string, any>[] = [];
  const doc: Document = { id: "report", revision: 5, publication: { shareId: "one", revision: 5 },
    annotationAccess: { endpoint: "/s/one/api/annotations", scope: "share:one", canRead: true,
      canAnnotate: false, canManageAnnotations: false, author: { name: "访客", verified: false } },
    manifest: { title: "固定的 A 版", viewMode: "filtered-report", report: { markdown: "原报告中的经营判断。" },
      components: {}, filters: [], layout: {}, metrics: {}, datasets: {}, annotations: [] },
    snapshot: { datasets: {} } };
  const requests: { url: string; body?: any }[] = [];
  globalThis.fetch = (async (url: RequestInfo | URL, init?: RequestInit) => {
    requests.push({ url: String(url), body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (String(url).endsWith("document.json")) return Response.json(doc);
    if (init?.method === "POST") {
      const body = JSON.parse(String(init.body));
      const annotation = { ...body.append, author: { name: body.authorName || "访客", verified: false } };
      notes.push(annotation);
      return Response.json({ revision: 5, annotation });
    }
    return Response.json({ revision: 5, annotations: notes, canAnnotate: true, canManageAnnotations: false });
  }) as typeof fetch;
  try {
    const first = render(<TooltipProvider><StaticSite /></TooltipProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "查看批注" }));
    await waitFor(() => expect(document.querySelector("[data-annotation-picking]")).toBeTruthy());
    fireEvent.keyDown(screen.getByText("原报告中的经营判断。"), { key: "Enter" });
    fireEvent.change(await screen.findByRole("textbox", { name: "批注内容" }), { target: { value: "请解释这个判断" } });
    fireEvent.change(screen.getByRole("textbox", { name: "署名（可选）" }), { target: { value: "读者甲" } });
    const submit = screen.getByRole("button", { name: "提交批注" }) as HTMLButtonElement;
    await waitFor(() => expect(submit.disabled).toBe(false));
    fireEvent.click(submit);
    await screen.findByRole("button", { name: "批注列表（1）" });
    expect((screen.getByRole("button", { name: "编辑布局" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "版本与分享" }) as HTMLButtonElement).disabled).toBe(true);
    expect(notes[0].anchor).toMatchObject({ scope: "text", quote: "原报告中的经营判断。", occurrence: 0 });
    expect(notes[0].view.revision).toBe(5);
    expect(requests.filter(request => request.body)).toHaveLength(1);
    expect(requests.filter(request => request.url.endsWith("document.json"))).toHaveLength(1);
    first.unmount();
    render(<TooltipProvider><StaticSite /></TooltipProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "查看批注" }));
    await waitFor(() => expect(document.querySelector("[data-annotation-picking]")).toBeTruthy());
    fireEvent.click(await screen.findByRole("button", { name: "批注列表（1）" }));
    fireEvent.click(await screen.findByRole("button", { name: /页面位置.*请解释这个判断/ }));
    expect(await screen.findByText("请解释这个判断")).toBeTruthy();
    expect(screen.getByText(/读者甲 · 未验证署名 · 版本 5/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "修改批注" })).toBeNull();
    expect(screen.queryByRole("button", { name: "删除批注" })).toBeNull();
    expect(screen.getByRole("heading", { name: "固定的 A 版" })).toBeTruthy();
  } finally {
    cleanup(); window.sessionStorage.clear();
    window.HTMLElement.prototype.getBoundingClientRect = originalRect;
    keys.forEach((key, index) => {
      if (descriptors[index]) Object.defineProperty(globalThis, key, descriptors[index]!);
      else Reflect.deleteProperty(globalThis, key);
    });
  }
});
