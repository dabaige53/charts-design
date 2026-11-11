// Migrated from aefb7e857663a42a6bb426f8b5ba3eca48cb950e; business data comes through props.
import type { ChartDefinition } from "./types";
const formatDelta = (value: number) => `${value > 0 ? "+" : ""}${value}`;
const definition: ChartDefinition = {
  code: "fn01",
  optionBuilder: (d: any, gran: any, tokens: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const seriesLabel = (presentation.seriesLabels || ["变化值"])[0];
    const tooltipLabel = (presentation.tooltipValueLabels || [seriesLabel])[0];
    const unit = (presentation.units || [cfg.unit || ""])[0];
    const yDomain = (presentation.domains || {}).y || {};
    const formatDelta = (value: any) =>
      `${value > 0 ? "+" : ""}${value}${unit ? ` ${unit}` : ""}`;
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
          const idx = params[0].dataIndex;
          const val = d.deltas[idx];
          return `<div class="font-bold text-primary-strong mb-1">${params[0].name}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">${tooltipLabel}:</span><span class="font-mono font-bold ${val >= 0 ? "text-positive" : "text-negative"}">${formatDelta(val)}</span></div>`;
        },
      },
      xAxis: {
        type: "category",
        name: axisLabels.x || "类别",
        nameLocation: "middle",
        nameGap: 20,
        nameTextStyle: tokens.axisTitleStyleX,
        data: d.categories,
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        ...yDomain,
        name: axisLabels.y || `${seriesLabel}${unit ? ` (${unit})` : ""}`,
        nameLocation: "end",
        nameTextStyle: tokens.axisTitleStyleY,
        axisLabel: {
          formatter: (value: any) => `${value}${unit ? ` ${unit}` : ""}`,
        },
        splitLine: { lineStyle: { color: tokens.palette.gridline } },
      },
      series: [
        {
          type: "bar",
          stack: "total",
          itemStyle: { borderColor: "transparent", color: "transparent" },
          data: d.baseSteps,
        },
        {
          type: "bar",
          stack: "total",
          barWidth: 22,
          name: seriesLabel,
          data: d.deltas.map((value: any, index: any) => ({
            value: Math.abs(value),
            itemStyle: {
              color:
                index === 0
                  ? tokens.palette.primary
                  : index === d.deltas.length - 1
                    ? tokens.palette.primaryStrong
                    : value >= 0
                      ? tokens.palette.positive
                      : tokens.palette.negative,
            },
          })),
          label: {
            show: true,
            position: "top",
            formatter: (params: any) => formatDelta(d.deltas[params.dataIndex]),
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
    const seriesLabel = (presentation.seriesLabels || ["变化值"])[0];
    const unit = (presentation.units || [cfg.unit || ""])[0];
    const labels = presentation.labels || {};
    return {
      headers: presentation.tableHeaders || [
        axisLabels.x || "类别",
        `${seriesLabel}${unit ? ` (${unit})` : ""}`,
        labels.directionHeader || "方向",
      ],
      rows: d.categories.map((c: any, i: any) => [
        c,
        `${d.deltas[i] > 0 ? "+" : ""}${d.deltas[i]}${unit ? ` ${unit}` : ""}`,
        d.deltas[i] >= 0
          ? labels.positive || "正向"
          : labels.negative || "负向",
      ]),
    };
  },
};
export default definition;
