import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import React from "react";
import { VersionCenter } from "./version-center";
import type { Document } from "./types";

Object.defineProperty(globalThis, "CustomEvent", { configurable: true, value: window.CustomEvent });
Object.defineProperty(globalThis, "NodeFilter", { configurable: true, value: window.NodeFilter });
afterEach(cleanup);

// @wu-test type=integration | scope=VersionCenter 删除历史 | protects=未经确认删除历史或允许删除已发布与最新保存版本
it("requires confirmation before deleting an eligible checkpoint", async () => {
  const doc = { id: "board", revision: 3, manifest: { title: "Board", components: {}, datasets: {} } } as Document;
  const call = mock(async (name: string) => {
    if (name === "dashboard_version_status") return { draftRevision: 3, savedRevision: 3, publishedRevision: 1, releases: [{ id: 1, revision: 1 }] };
    if (name === "dashboard_history") return { history: [{ revision: 1 }, { revision: 2 }, { revision: 3 }] };
    return { deleted: true };
  });
  render(<VersionCenter open onOpenChange={() => {}} document={doc} call={call} onRestore={async () => {}} onSaved={async () => {}} />);
  await waitFor(() => expect(screen.getAllByRole("button", { name: "删除版本" })).toHaveLength(3));
  const buttons = screen.getAllByRole("button", { name: "删除版本" }) as HTMLButtonElement[];
  expect(buttons.map((button) => button.disabled)).toEqual([true, false, true]);
  fireEvent.click(buttons[1]);
  expect(call.mock.calls.some(([name]) => name === "dashboard_version_delete")).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
  await waitFor(() => expect(call.mock.calls.some(([name]) => name === "dashboard_version_delete")).toBe(true));
});
