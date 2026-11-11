import { describe, it, expect } from "vitest";
import definitions from "../fixtures/charts.json";
import { chartOption, chartData } from "./chart";

describe("图表组件", () => {
  // @wu-test type=behavior | scope=chartOption | protects=预设返回空配置导致图表空白
  it("为每个预设生成可绘制的数据系列", () => {
    for (const definition of Object.values(definitions)) {
      const series = chartOption(definition).series;
      expect(series.length, definition.code).toBeGreaterThan(0);
      expect(series.every((item: { type: string }) => typeof item.type === "string"), definition.code).toBe(true);
    }
  });
  // @wu-test type=behavior | scope=chartData | protects=图表切换数据表时丢失明细或表头
  it("为预设示例生成明细和表头", () => {
    for (const definition of Object.values(definitions)) {
      const table = chartData(definition);
      expect(table.headers.length, definition.code).toBeGreaterThan(0);
      expect(table.rows.length, definition.code).toBeGreaterThan(0);
    }
  });
  // @wu-test type=behavior | scope=自由ECharts配置 | protects=自定义系列和几何被预设覆盖或显式数据表丢失
  it("保留自定义配置和显式明细", () => {
    const config = {
      code: "custom-radar", renderer: "echarts",
      echarts: { radar: { center: ["30%", "40%"] }, series: [{ type: "radar", data: [{ value: [2, 3] }] }] },
      table: { headers: ["A", "B"], rows: [[2, 3]] },
    };
    const option = chartOption(config);
    expect(option.radar.center).toEqual(["30%", "40%"]);
    expect(option.series).toEqual([{ type: "radar", data: [{ value: [2, 3] }] }]);
    expect(chartData(config)).toEqual({ headers: ["A", "B"], rows: [[2, 3]] });
    expect(() => chartData({ renderer: "html", html: "<p>2</p>" })).toThrow("未声明数据表");
  });
});
