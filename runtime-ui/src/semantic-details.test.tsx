import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "bun:test";
import { SemanticDetails } from "./semantic-details";
import type { Document } from "./types";

afterEach(cleanup);

// @wu-test type=behavior | scope=SemanticDetails KPI 对比 | protects=同一指标的基期重复显示且不同定义被错误隐藏
it("shows one definition for matching comparison baselines and retains distinct definitions", () => {
  const base = { datasetId: "data", label: "中转量", definition: "中转总量", unit: "条", aggregation: "sum" };
  const document: Document = { id: "board", revision: 1, manifest: {
    title: "Board", components: {}, filters: [], layout: {}, datasets: { data: { fields: {} } },
    metrics: { current: { ...base, field: "current" }, prior: { ...base, field: "prior" },
      other: { ...base, field: "other", definition: "不同的统计范围" } },
  }, snapshot: { datasets: {} } };
  const component = { kind: "kpi", family: "kpi", datasetId: "data", measures: ["current", "prior", "other"],
    binding: { measures: { value: "current", yoy: "prior", mom: "other" }, comparisons: {
      yoy: { current: "value", baseline: "yoy" }, mom: { current: "value", baseline: "mom" },
    } } };
  const { container } = render(<SemanticDetails value={{}} component={component} document={document} componentId="kpi" filters={[]} />);
  expect(container.querySelectorAll(".semantic-metric")).toHaveLength(2);
  expect(screen.getByText("中转总量")).toBeTruthy();
  expect(screen.getByText("不同的统计范围")).toBeTruthy();
  expect(container.querySelectorAll(".semantic-metric-unit")).toHaveLength(2);
});
