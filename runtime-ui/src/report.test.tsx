import { expect, test } from "bun:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ReportView } from "./report";
import type { Document } from "./types";

// @wu-test type=behavior | scope=筛选式报告渲染 | protects=宽表挤进论文窄栏或表级筛选脱离所属表
test("renders subsection text and table filters in the wide report", () => {
  const document = { manifest: { viewMode: "filtered-report", components: {
    a: { kind: "table", title: "A" }, b: { kind: "table", title: "B" },
  }, report: { markdown: '# 标题\n\n### 甲小节\n\n文字一\n\n```chart\n{"componentId":"a"}\n```\n\n### 乙小节\n\n文字二\n\n```chart\n{"componentId":"b","caption":"乙表"}\n```' } } } as unknown as Document;
  const html = renderToStaticMarkup(<ReportView document={document} component={(id) => <div>表格{id}</div>} tableFilters={(id) => <div>筛选{id}</div>} />);
  expect(html).toContain('class="prose-report prose-report-filtered"');
  expect(html).not.toContain("表 1");
  expect(html).toContain("表 2　乙表");
  expect(html).not.toContain("h-[420px]");
  expect(html.indexOf("<h3>甲小节</h3>")).toBeLessThan(html.indexOf("文字一"));
  expect(html.indexOf("文字一")).toBeLessThan(html.indexOf("筛选a"));
  expect(html.indexOf("筛选a")).toBeLessThan(html.indexOf("表格a"));
  expect(html.indexOf("表格a")).toBeLessThan(html.indexOf("文字二"));
  expect(html.indexOf("文字二")).toBeLessThan(html.indexOf("筛选b"));
});
