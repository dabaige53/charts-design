import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import React from "react";
import { TooltipProvider } from "./components/ui/tooltip";
import { PositionComments } from "./position-comments";
import type { Config, Document } from "./types";

afterEach(cleanup);

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
