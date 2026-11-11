// Migrated from aefb7e857663a42a6bb426f8b5ba3eca48cb950e; business data comes through props.
import type { ChartDefinition } from "./types";
const definition: ChartDefinition = {
  code: "k02",
  optionBuilder: (d: any, gran: any, tokens: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const seriesLabels = presentation.seriesLabels || [
      "系列 1",
      "系列 2",
      "系列 3",
    ];
    const tooltipLabels = presentation.tooltipValueLabels || seriesLabels;
    const units = presentation.units || ["%", "%", "%"];
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
            res += `<div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">${tooltipLabels[index]}:</span><span class="font-mono font-bold text-primary">${p.value}${units[index] ? ` ${units[index]}` : ""}</span></div>`;
          });
          return res;
        },
      },
      legend: {
        top: 0,
        right: 12,
        orient: "horizontal",
        icon: "rect",
        itemWidth: 10,
        itemHeight: 10,
        itemGap: 12,
        data: seriesLabels,
        textStyle: { fontSize: 10, color: tokens.palette.inkMuted },
      },
      grid: { top: 38, bottom: 38, left: 10, right: 25, containLabel: true },
      xAxis: {
        type: "value",
        name: axisLabels.x || "占比",
        nameLocation: "middle",
        nameGap: 24,
        nameTextStyle: tokens.axisTitleStyleX,
        axisLabel: { formatter: (value: any) => `${value}${units[0] || ""}` },
        splitLine: { lineStyle: { color: tokens.palette.gridline } },
      },
      yAxis: {
        type: "category",
        inverse: true,
        name: axisLabels.y || "类别",
        nameLocation: "start",
        nameTextStyle: tokens.axisTitleStyleY,
        data: d.hubs,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "#94A3B8", width: 1.2 } },
        axisLabel: { color: "#0F172A", fontSize: 12, fontWeight: 700 },
      },
      series: [
        {
          name: seriesLabels[0],
          type: "bar",
          stack: "total",
          barWidth: 18,
          data: d.appDirect,
          itemStyle: { color: "#0B2A42" },
          label: {
            show: true,
            formatter: (params: any) => `${params.value}${units[0] || ""}`,
            color: "#FFF",
            fontSize: 9,
          },
        },
        {
          name: seriesLabels[1],
          type: "bar",
          stack: "total",
          data: d.corpDirect,
          itemStyle: { color: "#123B5D" },
          label: {
            show: true,
            formatter: (params: any) => `${params.value}${units[1] || ""}`,
            color: "#FFF",
            fontSize: 9,
          },
        },
        {
          name: seriesLabels[2],
          type: "bar",
          stack: "total",
          data: d.ota,
          itemStyle: { color: "#8EA4B8" },
          label: {
            show: true,
            formatter: (params: any) => `${params.value}${units[2] || ""}`,
            color: "#FFF",
            fontSize: 9,
          },
        },
      ],
    };
  },
  tableDataExtractor: (d: any, gran: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const seriesLabels = presentation.seriesLabels || [
      "系列 1",
      "系列 2",
      "系列 3",
    ];
    const units = presentation.units || ["%", "%", "%"];
    return {
      headers: presentation.tableHeaders || [
        axisLabels.y || "类别",
        ...seriesLabels,
      ],
      rows: d.hubs.map((h: any, i: any) => [
        h,
        `${d.appDirect[i]}${units[0] ? ` ${units[0]}` : ""}`,
        `${d.corpDirect[i]}${units[1] ? ` ${units[1]}` : ""}`,
        `${d.ota[i]}${units[2] ? ` ${units[2]}` : ""}`,
      ]),
    };
  },
};
export default definition;
