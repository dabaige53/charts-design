import { expect, spyOn, test } from "bun:test";
import * as echarts from "echarts";
import { chartOption } from "../chart";
import type { Config, Document } from "../types";
import { adaptOption } from "./adaptive";

const seriesNames = ["同比（%）", "环比（%）", "去年同期销量（张）", "授权渠道吉祥销量（张）"];
const axisNames = ["净销量（张）", "变动（%）", "航班月"];

function trendOption(dual: boolean) {
  const names = dual ? seriesNames : seriesNames.slice(2);
  const values = [[5, -13, 4, 8], [-10, 7, -4, 9], [80, 88, 105, 98], [84, 90, 103, 111]];
  const config = {
    code: "c03",
    encoding: { orientation: "vertical", topSeries: 4, pinnedSeries: names },
    data: {
      records: ["2026-07", "2026-08", "2026-09", "2026-10"].flatMap((category, month) =>
        names.map((series) => ({ category, series, values: { value: values[seriesNames.indexOf(series)][month] } }))),
    },
    echarts: {
      xAxis: { name: axisNames[2] },
      yAxis: [
        { name: axisNames[0] },
        ...(dual ? [{ type: "value", name: axisNames[1], min: -15, max: 15, interval: 5, axisLabel: { formatter: "{value}%" } }] : []),
      ],
      ...(dual ? { series: [{ yAxisIndex: 1 }, { yAxisIndex: 1 }, { type: "line" }, { type: "line" }] } : {}),
    },
  };
  const document = {
    manifest: {
      components: { trend: { config, binding: { measures: { value: "amount" } } } },
      metrics: { amount: { aggregation: "avg", decimals: 1 } },
    },
  } as unknown as Document;
  return chartOption(config, "month", { document, id: "trend" });
}

function renderText(option: Config, width: number, height = 320) {
  const canvas = spyOn(window.HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  const chart = echarts.init(null, undefined, { renderer: "svg", ssr: true, width, height });
  try {
    chart.setOption({ ...adaptOption(option, width, height), animation: false });
    chart.renderToSVGString();
    const texts = chart.getZr().storage.getDisplayList().flatMap((element) => {
      if (element.type !== "tspan") return [];
      const bounds = element.getBoundingRect().clone();
      if (element.transform) bounds.applyTransform(element.transform);
      return [{ text: (element as unknown as { style: { text: string } }).style.text, bounds }];
    });
    return (label: string) => {
      const matches = texts.filter(({ text }) => text === label);
      expect(matches).toHaveLength(1);
      return matches[0].bounds;
    };
  } finally {
    chart.dispose();
    canvas.mockRestore();
  }
}

// @wu-test type=regression | scope=双轴图表自适应布局 | protects=INS-282 图例压住纵轴名或横轴名覆盖右轴最低刻度
test("renders all legend entries and axis names in separate space on dual-axis cards", () => {
  for (const [width, height] of [[560, 320], [660, 320], [740, 320], [560, 208]]) {
    const option = trendOption(true);
    const seriesData = () => option.series.map(({ name, type, yAxisIndex, data }: Config) => ({ name, type, yAxisIndex, data }));
    const series = structuredClone(seriesData());
    const text = renderText(option, width, height);
    expect(seriesData()).toEqual(series);
    const legendBottom = Math.max(...seriesNames.map((name) => {
      const bounds = text(name);
      expect(bounds.x).toBeGreaterThanOrEqual(0);
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
      return bounds.y + bounds.height;
    }));
    expect(text(axisNames[0]).y - legendBottom).toBeGreaterThanOrEqual(4);
    expect(text(axisNames[1]).y - legendBottom).toBeGreaterThanOrEqual(4);
    const xName = text(axisNames[2]);
    const tick = text("-15%");
    expect(xName.x - (tick.x + tick.width)).toBeGreaterThanOrEqual(4);
    expect(xName.x + xName.width).toBeLessThanOrEqual(width);
  }
});

// @wu-test type=behavior | scope=单轴图表自适应布局 | protects=单轴图被切换到双轴布局或横轴名超出卡片
test("keeps the existing single-axis layout and renders its axis names", () => {
  const width = 560;
  const option = trendOption(false);
  const text = renderText(option, width);
  expect(option.grid.containLabel).toBe(true);
  const xName = text(axisNames[2]);
  expect(xName.x + xName.width).toBeLessThanOrEqual(width);
  const yName = text(axisNames[0]);
  expect(yName.y).toBeGreaterThanOrEqual(0);
  for (const name of seriesNames.slice(2)) expect(text(name).width).toBeGreaterThan(0);
});
