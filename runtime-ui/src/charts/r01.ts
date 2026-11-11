// Migrated from aefb7e857663a42a6bb426f8b5ba3eca48cb950e; business data comes through props.
import type { ChartDefinition } from "./types";
const definition: ChartDefinition = {
  code: "r01",
  optionBuilder: (d: any, gran: any, tokens: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const tooltipLabels = presentation.tooltipValueLabels || [
      axisLabels.x || "X 值",
      axisLabels.y || "Y 值",
    ];
    const seriesLabel = (presentation.seriesLabels || ["数据点"])[0];
    const units = presentation.units || ["", ""];
    const thresholds = presentation.thresholds || { x: 0, y: 0 };
    const quadrant = (x: any, y: any) =>
      x >= thresholds.x
        ? y >= thresholds.y
          ? "第一象限"
          : "第四象限"
        : y >= thresholds.y
          ? "第二象限"
          : "第三象限";
    return {
      ...tokens.commonOption,
      tooltip: {
        backgroundColor: "rgba(255, 255, 255, 0.98)",
        borderColor: tokens.palette.rule,
        borderWidth: 1,
        padding: [8, 12],
        extraCssText:
          "box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;",
        formatter: (params: any) =>
          `<div class="font-bold text-primary-strong mb-1">${params.data[2]}</div><div class="space-y-0.5"><div class="flex justify-between gap-4"><span class="text-ink-muted">${tooltipLabels[0]}:</span><span class="font-mono font-bold text-positive">${params.data[0]}${units[0] ? ` ${units[0]}` : ""}</span></div><div class="flex justify-between gap-4"><span class="text-ink-muted">${tooltipLabels[1]}:</span><span class="font-mono font-bold text-primary">${params.data[1]}${units[1] ? ` ${units[1]}` : ""}</span></div></div>`,
      },
      xAxis: {
        type: "value",
        name: axisLabels.x || "X 轴",
        nameLocation: "middle",
        nameGap: 24,
        nameTextStyle: tokens.axisTitleStyleX,
        axisLabel: { formatter: (value: any) => `${value}${units[0] || ""}` },
        splitLine: { lineStyle: { color: tokens.palette.gridline } },
      },
      yAxis: {
        type: "value",
        name: axisLabels.y || "Y 轴",
        nameLocation: "end",
        nameTextStyle: tokens.axisTitleStyleY,
        axisLabel: { formatter: (value: any) => `${value}${units[1] || ""}` },
        splitLine: { lineStyle: { color: tokens.palette.gridline } },
      },
      series: [
        {
          name: seriesLabel,
          type: "scatter",
          symbolSize: 14,
          itemStyle: {
            color: tokens.palette.primary,
            borderColor: "#FFF",
            borderWidth: 2,
          },
          data: d.routes,
          label: {
            show: true,
            position: "top",
            formatter: (params: any) => params.data[2],
            color: tokens.palette.ink,
            fontSize: 10,
            fontWeight: 600,
          },
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { type: "dashed", color: tokens.palette.rule, width: 1 },
            data: [{ xAxis: thresholds.x }, { yAxis: thresholds.y }],
          },
        },
      ],
    };
  },
  tableDataExtractor: (d: any, gran: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const units = presentation.units || ["", ""];
    const thresholds = presentation.thresholds || { x: 0, y: 0 };
    const quadrant = (x: any, y: any) =>
      x >= thresholds.x
        ? y >= thresholds.y
          ? "第一象限"
          : "第四象限"
        : y >= thresholds.y
          ? "第二象限"
          : "第三象限";
    return {
      headers: presentation.tableHeaders || [
        "对象",
        axisLabels.x || "X 值",
        axisLabels.y || "Y 值",
        "象限",
      ],
      rows: d.routes.map((r: any) => [
        r[2],
        `${r[0]}${units[0] ? ` ${units[0]}` : ""}`,
        `${r[1]}${units[1] ? ` ${units[1]}` : ""}`,
        quadrant(r[0], r[1]),
      ]),
    };
  },
};
export default definition;
