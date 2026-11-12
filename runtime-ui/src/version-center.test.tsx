import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import React from "react";
import { VersionCenter } from "./version-center";
import type { Config, Document } from "./types";

Object.defineProperty(globalThis, "CustomEvent", { configurable: true, writable: true, value: window.CustomEvent });
Object.defineProperty(globalThis, "NodeFilter", { configurable: true, writable: true, value: window.NodeFilter });
afterEach(cleanup);
const doc = { id: "board", revision: 3, manifest: { title: "总览", components: {}, datasets: {} } } as Document;

// @wu-test type=integration | scope=VersionCenter 删除历史 | protects=删除影响未返回时无反馈或未确认就删除最新版本
it("shows pending impact and requires confirmation before deleting the latest checkpoint", async () => {
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
  fireEvent.click(screen.getAllByRole("button", { name: "删除版本" })[0]);
  await screen.findByText("正在检查删除影响…");
  expect(screen.queryByRole("button", { name: "确认删除" })).toBeNull();
  expect(call.mock.calls.some(([name]) => name === "dashboard_version_delete")).toBe(false);
  resolvePlan({ token: "checked-plan", shares: [], nextSavedRevision: 2 });
  fireEvent.click(await screen.findByRole("button", { name: "确认删除" }));
  await waitFor(() => expect(call.mock.calls.some(([name]) => name === "dashboard_version_delete")).toBe(true));
  expect(call.mock.calls.find(([name]) => name === "dashboard_version_delete")?.[1]).toEqual({ dashboardId: "board", expectedRevision: 3, revision: 3, confirmation: "checked-plan" });
});

// @wu-test type=integration | scope=VersionCenter 删除影响 | protects=数据库失败后没有错误提示或无法重试
it("reports a failed impact preview without deleting and enables retry", async () => {
  const call = mock(async (name: string) => {
    if (name === "dashboard_version_status") return { draftRevision: 3, savedRevision: 3 };
    if (name === "dashboard_history") return { history: [{ revision: 3 }] };
    throw Error("无法检查删除影响");
  });
  render(<VersionCenter open onOpenChange={() => {}} document={doc} call={call} onRestore={async () => {}} onSaved={async () => {}} />);
  fireEvent.click(await screen.findByRole("button", { name: "删除版本" }));
  await screen.findByText("无法检查删除影响");
  await waitFor(() => expect((screen.getByRole("button", { name: "删除版本" }) as HTMLButtonElement).disabled).toBe(false));
  expect(call.mock.calls.some(([name]) => name === "dashboard_version_delete")).toBe(false);
});

// @wu-test type=integration | scope=VersionCenter 版本命名冲突 | protects=版本变化后丢失输入名称或未加载最新内容就重试
it("preserves the entered name after a revision conflict", async () => {
  let revision = 3;
  const call = mock(async (name: string, _args?: Config) => {
    if (name === "dashboard_version_status") return { draftRevision: revision, savedRevision: 3 };
    if (name === "dashboard_history") return { history: [{ revision: 3, published: 1 }] };
    if (name === "dashboard_version_label") {
      if (revision === 3) { revision = 4; throw Object.assign(Error("REVISION_CONFLICT"), { code: "REVISION_CONFLICT" }); }
      return {};
    }
    return {};
  });
  render(<VersionCenter open onOpenChange={() => {}} document={doc} call={call} onRestore={async () => {}} onSaved={async () => {}} />);
  fireEvent.click(await screen.findByRole("button", { name: "修改版本名称" }));
  const input = screen.getByLabelText("版本名称") as HTMLInputElement;
  fireEvent.change(input, { target: { value: "123456" } });
  fireEvent.click(screen.getByRole("button", { name: "保存名称" }));
  await screen.findByText("内容已在别处更新。请先加载最新内容，检查后再操作。");
  expect(input.value).toBe("123456");
  expect((screen.getByRole("button", { name: "保存名称" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "加载最新内容" }));
  await screen.findByText("已加载最新内容，请检查后重新操作。");
  fireEvent.click(screen.getByRole("button", { name: "保存名称" }));
  await screen.findByText("版本 3 的名称已更新。");
  expect(call.mock.calls.filter(([name]) => name === "dashboard_version_label").at(-1)?.[1]).toEqual({ dashboardId: "board", expectedRevision: 4, revision: 3, name: "123456", published: true });
});

// @wu-test type=integration | scope=VersionCenter 分享状态 | protects=过期分享的副本清理被误认为删除已保存版本
it("distinguishes an expired share from a saved version", async () => {
  const call = mock(async (name: string) => {
    if (name === "dashboard_version_status") return { draftRevision: 15, savedRevision: 15, publishedRevision: 14 };
    if (name === "dashboard_history") return { history: [] };
    if (name === "dashboard_share_status") return { shares: [{ shareId: "old", url: "https://example.test/old", state: "expired", revision: 14, cleanupState: "pending", expiresAt: 1700000000, pages: [] }] };
    if (name === "dashboard_list") return { dashboards: [] };
    return {};
  });
  render(<VersionCenter open onOpenChange={() => {}} document={doc} call={call} onRestore={async () => {}} onSaved={async () => {}} />);
  fireEvent.click(await screen.findByRole("tab", { name: "分享链接" }));
  fireEvent.click(await screen.findByRole("button", { name: /展开分享/ }));
  await screen.findByText("此分享已失效，分享副本将自动删除；保存的版本不受影响。");
  expect(screen.getByText("已过期")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "更新到最新版本" })).toBeNull();
});

// @wu-test type=integration | scope=VersionCenter 多页面分享 | protects=创建分享使用发布版本或选入没有保存版本的页面
it("uses each page's latest saved revision when creating a share", async () => {
  const call = mock(async (name: string, args?: Config) => {
    if (name === "dashboard_version_status") return { draftRevision: 14, savedRevision: args?.dashboardId === "unpublished" ? null : args?.dashboardId === "other" ? 8 : 14, publishedRevision: 1 };
    if (name === "dashboard_history") return { history: [] };
    if (name === "dashboard_share_status") return { shares: [] };
    if (name === "dashboard_list") return { dashboards: [{ id: "board", title: "总览" }, { id: "other", title: "其他页" }, { id: "unpublished", title: "未保存页" }] };
    if (name === "dashboard_share_publish") return { shareId: "new", url: "https://example.test/new", accessKey: "12345678" };
    return {};
  });
  render(<VersionCenter open onOpenChange={() => {}} document={doc} call={call} onRestore={async () => {}} onSaved={async () => {}} />);
  fireEvent.click(await screen.findByRole("tab", { name: "分享链接" }));
  fireEvent.click(await screen.findByRole("button", { name: "创建分享" }));
  const dialog = screen.getByRole("dialog", { name: "创建分享" });
  fireEvent.click(within(dialog).getByRole("checkbox", { name: "其他页 · 版本 8" }));
  expect((within(dialog).getByRole("checkbox", { name: "未保存页 · 尚未保存" }) as HTMLInputElement).disabled).toBe(true);
  fireEvent.click(within(dialog).getByRole("button", { name: "创建分享" }));
  await screen.findByText("分享已创建。");
  expect(call.mock.calls.find(([name]) => name === "dashboard_share_publish")?.[1]).toEqual({ dashboardId: "board", expectedRevision: 14, versionSource: "saved", expiration: "7d", pages: [{ dashboardId: "other", expectedRevision: 8 }] });
});

// @wu-test type=integration | scope=VersionCenter 批量更新 | protects=更新失败后丢失已生成密钥或继续更新未经确认的后续分享
it("retains successful credentials and stops on an uncertain batch failure", async () => {
  const shares = ["a", "b", "c"].map(id => ({ shareId: id, url: `https://example.test/${id}`, state: "active", revision: 1, pages: [{ id: "board", revision: 1 }, { id: "other", revision: 2 }] }));
  const call = mock(async (name: string, args?: Config) => {
    if (name === "dashboard_version_status") return { draftRevision: 3, savedRevision: args?.dashboardId === "other" ? 4 : 3 };
    if (name === "dashboard_history") return { history: [] };
    if (name === "dashboard_share_status") return { shares };
    if (name === "dashboard_list") return { dashboards: [{ id: "board", title: "总览" }, { id: "other", title: "其他页" }] };
    if (name === "dashboard_share_replace") {
      if (args?.shareId === "b") throw Error("network failure");
      return { shareId: "new-a", url: "https://example.test/new-a", accessKey: "12345678", previousRevoked: true };
    }
    return {};
  });
  render(<VersionCenter open onOpenChange={() => {}} document={doc} call={call} onRestore={async () => {}} onSaved={async () => {}} />);
  fireEvent.click(await screen.findByRole("tab", { name: "分享链接" }));
  fireEvent.click(await screen.findByLabelText("全选可访问的分享"));
  fireEvent.click(screen.getByRole("button", { name: "更新到最新版本（3）" }));
  const dialog = await screen.findByRole("dialog", { name: "更新 3 条分享至最新版本" });
  fireEvent.click(within(dialog).getByRole("button", { name: "确认更新 3 条分享" }));
  await screen.findByText(/已生成 1 条新链接。本条更新结果未确认/);
  expect(screen.getByText("12345678")).toBeTruthy();
  const requests = call.mock.calls.filter(([name]) => name === "dashboard_share_replace");
  expect(requests).toHaveLength(2);
  expect(requests[0][1]).toEqual({ dashboardId: "board", shareId: "a", expectedRevision: 3, versionSource: "saved", expiration: "7d", pages: [{ dashboardId: "other", expectedRevision: 4 }] });
});

// @wu-test type=integration | scope=VersionCenter 分享地址复制 | protects=复制已有分享时遗漏完整链接或误复制新密钥
it("copies the existing share URL without inventing a key", async () => {
  const writeText = mock(async (_value: string) => {});
  const previous = Object.getOwnPropertyDescriptor(navigator, "clipboard");
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  const call = mock(async (name: string) => {
    if (name === "dashboard_version_status") return { draftRevision: 3, savedRevision: 3 };
    if (name === "dashboard_history") return { history: [] };
    if (name === "dashboard_share_status") return { shares: [{ shareId: "a", url: "https://example.test/a/", state: "active", revision: 3, pages: [] }] };
    if (name === "dashboard_list") return { dashboards: [] };
    return {};
  });
  try {
    render(<VersionCenter open onOpenChange={() => {}} document={doc} call={call} onRestore={async () => {}} onSaved={async () => {}} />);
    fireEvent.click(await screen.findByRole("tab", { name: "分享链接" }));
    fireEvent.click(await screen.findByRole("button", { name: "复制链接" }));
    await screen.findByRole("button", { name: "已复制" });
    expect(writeText).toHaveBeenCalledWith("https://example.test/a/");
  } finally {
    if (previous) Object.defineProperty(navigator, "clipboard", previous);
    else Reflect.deleteProperty(navigator, "clipboard");
  }
});

// @wu-test type=integration | scope=VersionCenter 批量更新部分撤销失败 | protects=新密钥丢失或旧链接撤销失败后继续替换其他分享
it("keeps the new key and stops when the old link could not be revoked", async () => {
  const shares = ["a", "b"].map(id => ({ shareId: id, url: `https://example.test/${id}`, state: "active", revision: 1, pages: [] }));
  const call = mock(async (name: string) => {
    if (name === "dashboard_version_status") return { draftRevision: 3, savedRevision: 3 };
    if (name === "dashboard_history") return { history: [] };
    if (name === "dashboard_share_status") return { shares };
    if (name === "dashboard_list") return { dashboards: [{ id: "board", title: "总览" }] };
    if (name === "dashboard_share_replace") return { shareId: "new-a", url: "https://example.test/new-a", accessKey: "12345678", previousRevoked: false };
    return {};
  });
  render(<VersionCenter open onOpenChange={() => {}} document={doc} call={call} onRestore={async () => {}} onSaved={async () => {}} />);
  fireEvent.click(await screen.findByRole("tab", { name: "分享链接" }));
  fireEvent.click(await screen.findByLabelText("全选可访问的分享"));
  fireEvent.click(screen.getByRole("button", { name: "更新到最新版本（2）" }));
  const dialog = await screen.findByRole("dialog", { name: "更新 2 条分享至最新版本" });
  fireEvent.click(within(dialog).getByRole("button", { name: "确认更新 2 条分享" }));
  await screen.findByText(/其中一条旧链接撤销失败/);
  expect(screen.getByText("12345678")).toBeTruthy();
  expect(call.mock.calls.filter(([name]) => name === "dashboard_share_replace")).toHaveLength(1);
});
