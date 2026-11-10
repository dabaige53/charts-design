import { describe, it, expect } from "vitest";
import definitions from "../fixtures/charts.json";
import { chartOption, chartData } from "./chart";

describe("原版图表组件", () => {
  // @wu-test type=behavior | scope=chartOption | protects=原版图表配置无法生成导致画布图表空白
  it("为所有原版图表生成 ECharts 配置", () => {
    for (const definition of Object.values(definitions))
      expect(chartOption(definition)).toBeTruthy();
  });
  // @wu-test type=behavior | scope=chartData | protects=图表切换数据表时丢失原版明细
  it("为有数据提取器的图表生成表格", () => {
    for (const definition of Object.values(definitions))
      expect(chartData(definition).rows).toBeInstanceOf(Array);
  });
});
