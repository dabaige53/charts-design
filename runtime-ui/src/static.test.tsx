import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import { StaticSite } from "./static";
import type { Document } from "./types";

const originalFetch = globalThis.fetch;
const originalLocation = Object.getOwnPropertyDescriptor(globalThis, "location");
afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  if (originalLocation) Object.defineProperty(globalThis, "location", originalLocation);
  else Reflect.deleteProperty(globalThis, "location");
});

// @wu-test type=integration | scope=StaticSite 页面切换 | protects=多页面分享无法读取所选页面或误加载未选页面
it("loads selected pages from the shared site", async () => {
  Object.defineProperty(globalThis, "location", { configurable: true, value: new URL("https://charts.example/s/share/") });
  const pages = [
    { id: "first", title: "第一页", path: "document.json" },
    { id: "second", title: "第二页", path: "pages/second/document.json" },
  ];
  const documents = Object.fromEntries(pages.map(({ id, path, title }) => {
    const doc: Document = {
      id, revision: 1, staticPages: pages,
      manifest: { title, viewMode: "report", report: { markdown: "" },
        components: {}, filters: [], layout: {}, metrics: {}, datasets: {} },
      snapshot: { datasets: {} },
    };
    return [new URL(path, location.href).href, doc];
  }));
  const fetchMock = mock(async (url: RequestInfo | URL) => Response.json(documents[String(url)]));
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  render(<StaticSite />);
  await screen.findByRole("heading", { name: "第一页" });
  const select = await screen.findByRole("combobox", { name: "切换看板" });
  fireEvent.keyDown(select, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name: "第二页" }));
  await screen.findByRole("heading", { name: "第二页" });
  expect(fetchMock).toHaveBeenCalledTimes(2);
});
