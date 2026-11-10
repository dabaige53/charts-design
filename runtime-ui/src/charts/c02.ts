// Migrated from aefb7e857663a42a6bb426f8b5ba3eca48cb950e; business data comes through props.
import type { ChartDefinition } from "./types";
const definition: ChartDefinition = {
  code: "c02",
  optionBuilder: (d: any, gran: any, tokens: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const seriesLabel = (presentation.seriesLabels || ["数值"])[0];
    const tooltipLabel = (presentation.tooltipValueLabels || [seriesLabel])[0];
    const unit = (presentation.units || [cfg.unit || ""])[0];
    const scrollable = d.categories.length > 12;
    const categoryRange = {
      yAxisIndex: 0,
      startValue: 0,
      endValue: Math.min(11, d.categories.length - 1),
      rangeMode: ["value", "value"],
      filterMode: "filter",
    };
    return {
      ...tokens.commonOption,
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(255, 255, 255, 0.98)",
        borderColor: tokens.palette.rule,
        borderWidth: 1,
        padding: [8, 12],
        extraCssText:
          "box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;",
        formatter: (params: any) =>
          `<div class="font-bold text-primary-strong mb-1">${params[0].name}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">${tooltipLabel}:</span><span class="font-mono font-bold text-primary">${params[0].value}${unit ? ` ${unit}` : ""}</span></div>`,
      },
      grid: {
        top: 38,
        bottom: scrollable ? 76 : 38,
        left: 10,
        right: scrollable ? 58 : 40,
        containLabel: true,
      },
      toolbox: {
        show: scrollable,
        right: 0,
        top: 0,
        feature: { restore: { title: "重置缩放" } },
      },
      dataZoom: scrollable
        ? [
            {
              ...categoryRange,
              type: "inside",
              zoomOnMouseWheel: true,
              moveOnMouseWheel: false,
              moveOnMouseMove: true,
              preventDefaultMouseMove: true,
            },
            {
              ...categoryRange,
              type: "slider",
              orient: "vertical",
              right: 4,
              top: 38,
              bottom: 76,
              width: 14,
              showDetail: false,
              brushSelect: false,
            },
            {
              type: "slider",
              xAxisIndex: 0,
              start: 0,
              end: 100,
              filterMode: "none",
              bottom: 4,
              height: 16,
              showDetail: false,
              brushSelect: false,
            },
          ]
        : [],
      xAxis: {
        type: "value",
        splitNumber: 3,
        name: axisLabels.x || `${seriesLabel}${unit ? ` (${unit})` : ""}`,
        nameLocation: "middle",
        nameGap: 24,
        nameTextStyle: tokens.axisTitleStyleX,
        axisLabel: { hideOverlap: true, formatter: (value: any) => `${value}` },
        splitLine: { lineStyle: { color: tokens.palette.gridline } },
      },
      yAxis: {
        type: "category",
        inverse: true,
        name: axisLabels.y || "类别",
        nameLocation: "start",
        nameTextStyle: tokens.axisTitleStyleY,
        data: d.categories,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "#94A3B8", width: 1.2 } },
        axisLabel: {
          color: "#0F172A",
          fontSize: 12,
          fontWeight: 700,
          interval: scrollable ? 0 : "auto",
          width: 160,
          overflow: "truncate",
        },
      },
      series: [
        {
          name: seriesLabel,
          type: "bar",
          barWidth: 18,
          labelLayout: { hideOverlap: true },
          data: d.values,
          itemStyle: { color: tokens.palette.primary },
          label: {
            show: true,
            position: "right",
            distance: 6,
            formatter: (params: any) =>
              `${params.value}${unit ? ` ${unit}` : ""}`,
            color: tokens.palette.ink,
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
    const seriesLabel = (presentation.seriesLabels || ["数值"])[0];
    const unit = (presentation.units || [cfg.unit || ""])[0];
    return {
      headers: presentation.tableHeaders || [
        axisLabels.y || "类别",
        `${seriesLabel}${unit ? ` (${unit})` : ""}`,
      ],
      rows: d.categories.map((c: any, i: any) => [
        c,
        `${d.values[i]}${unit ? ` ${unit}` : ""}`,
      ]),
    };
  },
};
export default definition;
