// Migrated from aefb7e857663a42a6bb426f8b5ba3eca48cb950e; business data comes through props.
import type { ChartDefinition } from "./types";
const definition: ChartDefinition = {
  code: "fn03",
  optionBuilder: (d: any, gran: any, tokens: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const seriesLabels = presentation.seriesLabels || ["负向", "正向"];
    const tooltipLabels = presentation.tooltipValueLabels || seriesLabels;
    const unit = (presentation.units || [cfg.unit || ""])[0];
    const xDomain = (presentation.domains || {}).x || {};
    return {
      ...tokens.commonOption,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: "rgba(255, 255, 255, 0.98)",
        borderColor: tokens.palette.rule,
        borderWidth: 1,
        padding: [8, 12],
        extraCssText:
          "box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;",
        formatter: (params: any) => {
          let res = `<div class="font-bold text-primary-strong mb-1">${params[0].name}</div>`;
          params.forEach((p: any, index: any) => {
            res += `<div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">${tooltipLabels[index] || p.seriesName}:</span><span class="font-mono font-bold text-primary">${p.value}${unit ? ` ${unit}` : ""}</span></div>`;
          });
          return res;
        },
      },
      legend: {
        top: 0,
        left: "center",
        orient: "horizontal",
        icon: "rect",
        itemWidth: 10,
        itemHeight: 10,
        itemGap: 20,
        data: seriesLabels,
        textStyle: { fontSize: 10, color: tokens.palette.inkMuted },
      },
      grid: { top: 38, bottom: 38, left: 10, right: 30, containLabel: true },
      xAxis: {
        type: "value",
        ...xDomain,
        name: axisLabels.x || "数值",
        nameLocation: "middle",
        nameGap: 24,
        nameTextStyle: tokens.axisTitleStyleX,
        axisLabel: {
          formatter: (value: any) => `${value}${unit ? ` ${unit}` : ""}`,
        },
        splitLine: { lineStyle: { color: tokens.palette.gridline } },
      },
      yAxis: {
        type: "category",
        name: axisLabels.y || "变量",
        nameLocation: "start",
        nameTextStyle: tokens.axisTitleStyleY,
        data: d.variables,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "#94A3B8", width: 1.2 } },
        axisLabel: { color: "#0F172A", fontSize: 11, fontWeight: 700 },
      },
      series: [
        {
          name: seriesLabels[0],
          type: "bar",
          stack: "total",
          barWidth: 16,
          data: d.negative,
          itemStyle: { color: tokens.palette.negative },
          label: {
            show: true,
            position: "insideLeft",
            formatter: (params: any) =>
              `${params.value}${unit ? ` ${unit}` : ""}`,
            color: "#FFF",
            fontSize: 10,
            fontWeight: 600,
          },
        },
        {
          name: seriesLabels[1],
          type: "bar",
          stack: "total",
          barWidth: 16,
          data: d.positive,
          itemStyle: { color: tokens.palette.positive },
          label: {
            show: true,
            position: "insideRight",
            formatter: (params: any) =>
              `+${params.value}${unit ? ` ${unit}` : ""}`,
            color: "#FFF",
            fontSize: 10,
            fontWeight: 600,
          },
        },
      ],
    };
  },
  tableDataExtractor: (d: any, gran: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const seriesLabels = presentation.seriesLabels || ["负向", "正向"];
    const unit = (presentation.units || [cfg.unit || ""])[0];
    return {
      headers: presentation.tableHeaders || [
        axisLabels.y || "变量",
        `${seriesLabels[0]}${unit ? ` (${unit})` : ""}`,
        `${seriesLabels[1]}${unit ? ` (${unit})` : ""}`,
      ],
      rows: d.variables.map((v: any, i: any) => [
        v,
        `${d.negative[i]}${unit ? ` ${unit}` : ""}`,
        `+${d.positive[i]}${unit ? ` ${unit}` : ""}`,
      ]),
    };
  },
};
export default definition;
