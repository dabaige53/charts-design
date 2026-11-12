import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import React, { useEffect, useState } from "react";

mock.module("./dashboard", () => ({
  DashboardApp: ({ initial, call }: any) => {
    const [title, setTitle] = useState(initial.manifest.title);
    const [pages, setPages] = useState<any[]>([]);
    useEffect(() => { void call("dashboard_list").then((result: any) => setPages(result.dashboards)); }, []);
    return <><span>{title}</span>{pages.map((page) => <button key={page.id} onClick={() => void call("dashboard_get", { dashboardId: page.id }).then((result: any) => setTitle(result.document.manifest.title))}>{page.id}</button>)}</>;
  },
}));
import { StaticSite } from "./static";

const originalFetch = globalThis.fetch;
const originalLocation = Object.getOwnPropertyDescriptor(globalThis, "location");
afterEach(() => {
  cleanup(); globalThis.fetch = originalFetch; delete window.__chartsDocument; mock.restore();
  if (originalLocation) Object.defineProperty(globalThis, "location", originalLocation);
  else Reflect.deleteProperty(globalThis, "location");
});

// @wu-test type=integration | scope=StaticSite 页面切换 | protects=多页面分享无法读取所选页面或误加载未选页面
it("loads selected pages from the shared site", async () => {
  Object.defineProperty(globalThis, "location", { configurable: true, value: new URL("https://charts.example/s/share/") });
  const first = { id: "first", manifest: { title: "第一页" }, staticPages: [
    { id: "first", title: "第一页", path: "document.json" },
    { id: "second", title: "第二页", path: "pages/second/document.json" },
  ] };
  const fetchMock = mock(async (url: any) => ({ ok: true, json: async () => String(url).includes("pages/second/") ? { id: "second", manifest: { title: "第二页" } } : first }));
  globalThis.fetch = fetchMock as any;
  render(<StaticSite />);
  await screen.findByText("第一页");
  fireEvent.click(await screen.findByRole("button", { name: "second" }));
  await waitFor(() => expect(screen.getByText("第二页")).toBeTruthy());
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

// @wu-test type=performance | scope=StaticSite 首屏数据 | protects=应用启动后重复请求HTML已经开始加载的页面声明
it("consumes the document request started by the page shell", async () => {
  window.__chartsDocument = Promise.resolve({ id: "first", manifest: { title: "提前加载的页面" } } as any);
  const fetchMock = mock(async () => { throw Error("unexpected duplicate fetch"); });
  globalThis.fetch = fetchMock as any;
  render(<StaticSite />);
  await screen.findByText("提前加载的页面");
  expect(fetchMock).not.toHaveBeenCalled();
});
