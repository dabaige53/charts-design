import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import { VersionCenter } from "./version-center";
import type { Config, Document } from "./types";

Object.defineProperty(globalThis, "CustomEvent", { configurable: true, value: window.CustomEvent });
Object.defineProperty(globalThis, "NodeFilter", { configurable: true, value: window.NodeFilter });
afterEach(cleanup);

// @wu-test type=integration | scope=VersionCenter 快速发布 | protects=编辑器串行调用保存和发布或分享失败重试生成新请求
it("uses one publication call and reuses the share request on retry", async () => {
  const doc = { id: "board", revision: 3, manifest: { title: "Board", components: {}, datasets: {} } } as Document;
  const status = { draftRevision: 3, savedRevision: 2, publishedRevision: 2, releases: [] };
  let attempts = 0;
  const call = mock(async (name: string, _args?: Config) => {
    if (name === "dashboard_version_status") return status;
    if (name === "dashboard_history") return { history: [] };
    if (name !== "dashboard_publish") throw Error(`Unexpected tool ${name}`);
    const receipt = { ok: true, publishedRevision: 3, versionStatus: { ...status, savedRevision: 3, publishedRevision: 3 } };
    return ++attempts === 1
      ? { ...receipt, shareError: { message: "存储暂不可用" } }
      : { ...receipt, share: { url: "https://example.org/share", accessKey: "12345678" } };
  });
  render(<VersionCenter open onOpenChange={() => {}} document={doc} call={call} onRestore={async () => {}} onSaved={async () => {}} />);
  const button = await screen.findByRole("button", { name: "发布当前草稿" }) as HTMLButtonElement;
  await waitFor(() => expect(button.disabled).toBe(false));
  fireEvent.click(screen.getByRole("checkbox", { name: "同时生成分享链接" }));
  fireEvent.click(button);
  await screen.findByText("版本 3 已发布。分享链接生成失败：存储暂不可用");
  fireEvent.click(button);
  await screen.findByRole("link", { name: "https://example.org/share" });
  const actions = call.mock.calls.slice(2);
  expect(actions.map(([name]) => name)).toEqual(["dashboard_publish", "dashboard_publish"]);
  expect(actions[0][1]).toEqual(actions[1][1]);
});

// @wu-test type=integration | scope=VersionCenter 删除历史 | protects=删除影响未返回时无反馈或未确认就删除最新版本
it("shows pending impact and requires confirmation before deleting the latest checkpoint", async () => {
  const doc = { id: "board", revision: 3, manifest: { title: "Board", components: {}, datasets: {} } } as Document;
  let resolvePlan!: (value: Config) => void;
  const plan = new Promise<Config>((resolve) => { resolvePlan = resolve; });
  const call = mock(async (name: string, _args?: Config) => {
    if (name === "dashboard_version_status") return { draftRevision: 3, savedRevision: 3, publishedRevision: 1, releases: [{ id: 1, revision: 1 }] };
    if (name === "dashboard_history") return { history: [{ revision: 1 }, { revision: 2 }, { revision: 3 }] };
    if (name === "dashboard_version_delete_preview") return plan;
    return { state: "complete" };
  });
  render(<VersionCenter open onOpenChange={() => {}} document={doc} call={call} onRestore={async () => {}} onSaved={async () => {}} />);
  await waitFor(() => expect(screen.getAllByRole("button", { name: "删除版本" })).toHaveLength(3));
  const buttons = screen.getAllByRole("button", { name: "删除版本" }) as HTMLButtonElement[];
  expect(buttons.map((button) => button.disabled)).toEqual([false, false, false]);
  fireEvent.click(buttons[0]);
  await screen.findByText("正在检查删除影响…");
  expect(screen.queryByRole("button", { name: "确认删除" })).toBeNull();
  expect(call.mock.calls.some(([name]) => name === "dashboard_version_delete")).toBe(false);
  resolvePlan({ token: "checked-plan", objects: [], datasets: [], shares: [], retained: [],
    cosBytes: 0, postgresBytes: 0, checkedAt: "2026-11-12T00:00:00Z", nextSavedRevision: 2 });
  await screen.findByRole("button", { name: "确认删除" });
  fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
  await waitFor(() => expect(call.mock.calls.some(([name]) => name === "dashboard_version_delete")).toBe(true));
  expect(call.mock.calls.find(([name]) => name === "dashboard_version_delete")?.[1]).toEqual({
    dashboardId: "board", expectedRevision: 3, revision: 3, confirmation: "checked-plan",
  });
});

// @wu-test type=integration | scope=VersionCenter 删除影响 | protects=数据库失败后没有错误提示或无法重试
it("reports a failed impact preview without deleting and enables retry", async () => {
  const doc = { id: "board", revision: 2, manifest: { title: "Board", components: {}, datasets: {} } } as Document;
  const call = mock(async (name: string) => {
    if (name === "dashboard_version_status") return { draftRevision: 2, savedRevision: 2 };
    if (name === "dashboard_history") return { history: [{ revision: 2 }] };
    throw Error("无法检查删除影响");
  });
  render(<VersionCenter open onOpenChange={() => {}} document={doc} call={call} onRestore={async () => {}} onSaved={async () => {}} />);
  fireEvent.click(await screen.findByRole("button", { name: "删除版本" }));
  await screen.findByText("无法检查删除影响");
  await waitFor(() => expect((screen.getByRole("button", { name: "删除版本" }) as HTMLButtonElement).disabled).toBe(false));
  expect(call.mock.calls.some(([name]) => name === "dashboard_version_delete")).toBe(false);
});

// @wu-test type=integration | scope=VersionCenter 固定版本分享 | protects=分享历史版误发草稿、遗漏批注权限或失败后刷新重试生成重复分享
it("shares the selected saved version with independent annotation permission and a stable retry key", async () => {
  const doc = { id: "board", revision: 9, manifest: { title: "B版", components: {}, datasets: {} } } as Document;
  const status = { draftRevision: 9, savedRevision: 8, publishedRevision: 4, releases: [] };
  let attempts = 0;
  const call = mock(async (name: string, _args?: Config) => {
    if (name === "dashboard_version_status") return status;
    if (name === "dashboard_history") return { history: [{ revision: 4, name: "A版" }] };
    if (name === "dashboard_publish") {
      if (++attempts === 1) throw Error("分享服务暂不可用");
      return { ok: true, versionStatus: status, publishedRevision: 4,
        share: { url: "https://example.org/s/fixed/", accessKey: "12345678", annotationMode: "annotate" } };
    }
    throw Error(`Unexpected tool ${name}`);
  });
  const first = render(<VersionCenter open onOpenChange={() => {}} document={doc} call={call} onRestore={async () => {}} onSaved={async () => {}} />);
  fireEvent.change(screen.getByRole("combobox", { name: "分享权限" }), { target: { value: "annotate" } });
  fireEvent.click(await screen.findByRole("button", { name: "分享此版本" }));
  await screen.findByText("分享服务暂不可用");
  first.unmount();
  render(<VersionCenter open onOpenChange={() => {}} document={doc} call={call} onRestore={async () => {}} onSaved={async () => {}} />);
  fireEvent.click(await screen.findByRole("button", { name: "分享此版本" }));
  await screen.findByRole("link", { name: "https://example.org/s/fixed/" });
  const publications = call.mock.calls.filter(([name]) => name === "dashboard_publish");
  expect(publications).toHaveLength(2);
  expect(publications[0][1]).toEqual(publications[1][1]);
  expect(publications[0][1]).toMatchObject({ dashboardId: "board", revision: 4, expectedRevision: 9,
    share: { expiration: "7d", annotationMode: "annotate", requestId: expect.any(String) } });
});

// @wu-test type=integration | scope=VersionCenter 分享反馈 | protects=反馈打开当前草稿、反馈读取走MCP、受阻弹窗丢失原版访问入口
it("retrieves feedback on demand over HTTP and opens the frozen share rather than the draft", async () => {
  const originalFetch = globalThis.fetch;
  const originalOpen = window.open;
  const originalLocation = Object.getOwnPropertyDescriptor(globalThis, "location");
  Object.defineProperty(globalThis, "location", { configurable: true, value: window.location });
  window.open = mock(() => null);
  const fetchMock = mock(async (_url: RequestInfo | URL, _init?: RequestInit) => Response.json({
    url: "http://localhost/s/original/?feedback=signed", shareId: "original", revision: 4,
    annotations: [{ id: "note", text: "A版意见" }],
  }));
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  const doc = { id: "board", revision: 9, manifest: { title: "B版", components: {}, datasets: {} } } as Document;
  const call = mock(async (name: string) => {
    if (name === "dashboard_version_status") return { draftRevision: 9, savedRevision: 8, publishedRevision: 4 };
    if (name === "dashboard_history") return { history: [] };
    if (name === "dashboard_list") return { dashboards: [{ id: "board" }] };
    if (name === "dashboard_share_status") return { shares: [{ shareId: "original", revision: 4, state: "active", annotationMode: "annotate" }] };
    throw Error(`Unexpected tool ${name}`);
  });
  try {
    render(<VersionCenter open onOpenChange={() => {}} document={doc} call={call} onRestore={async () => {}} onSaved={async () => {}}
      publicationApiBase="/api/publications/" requestHeaders={() => ({ Authorization: "Bearer local-author" })} />);
    fireEvent.click(screen.getByRole("tab", { name: "分享" }));
    fireEvent.click(await screen.findByRole("button", { name: "查看读者批注" }));
    const link = await screen.findByRole("link", { name: "打开版本 4 的批注" });
    expect(link.getAttribute("href")).toBe("http://localhost/s/original/?feedback=signed");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://localhost/api/publications/original/feedback?dashboardId=board");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ cache: "no-store", headers: { Authorization: "Bearer local-author" } });
    expect(call.mock.calls.some(([name]) => /feedback|annotations|dashboard_get/.test(name))).toBe(false);
  } finally {
    cleanup(); globalThis.fetch = originalFetch; window.open = originalOpen;
    if (originalLocation) Object.defineProperty(globalThis, "location", originalLocation);
    else Reflect.deleteProperty(globalThis, "location");
  }
});
