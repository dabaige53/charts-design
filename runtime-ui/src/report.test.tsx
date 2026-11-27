import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ReportView } from "./report";
import type { Document } from "./types";

// @wu-test type=behavior | scope=论文报告渲染 | protects=论文题名、摘要和图注退回普通看板样式
test("renders academic report metadata and plot using dedicated presentation", () => {
  const document = {
    manifest: {
      viewMode: "report",
      components: { trend: { kind: "legacy", family: "chart", title: "收入趋势", config: { code: "t01" } } },
      report: { markdown: [
        "# 航线研究", "*2026 年第三季度*", "**摘要**　季度收入呈增长。", "**关键词：** 航线经营",
        "## 收入变化", "详见[图](#fig-trend)。", '```chart\n{"componentId":"trend"}\n```',
      ].join("\n\n") },
    },
  } as unknown as Document;
  const html = renderToStaticMarkup(<ReportView document={document} component={() => <canvas />} />);
  expect(html).toContain('<article class="prose-report">');
  expect(html).toContain('<p class="report-subtitle"><em>');
  expect(html).toContain('<p class="report-abstract"><strong>摘要</strong>');
  expect(html).toContain('<p class="report-keywords"><strong>关键词：</strong>');
  expect(html).toContain('<h2>1. 收入变化</h2>');
  expect(html).toContain('href="#fig-trend">图 1</a>');
  expect(html).toContain('data-report-monochrome="true"');
  expect(html).toContain("<figcaption>图 1　收入趋势</figcaption>");
});

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
