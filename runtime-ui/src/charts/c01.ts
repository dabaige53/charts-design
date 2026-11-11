// Migrated from aefb7e857663a42a6bb426f8b5ba3eca48cb950e; business data comes through props.
import type { ChartDefinition } from "./types";
const definition: ChartDefinition = {
  code: "c01",
  optionBuilder: (d: any, gran: any, tokens: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const seriesLabel = (presentation.seriesLabels || ["数值"])[0];
    const tooltipLabel = (presentation.tooltipValueLabels || [seriesLabel])[0];
    const unit = (presentation.units || [cfg.unit || ""])[0];
    const yDomain = (presentation.domains || {}).y || {};
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
          name: seriesLabel,
          type: "bar",
          barWidth: 26,
          data: d.values,
          itemStyle: { color: tokens.palette.primary },
          label: {
            show: true,
            position: "top",
            distance: 6,
            formatter: (params: any) =>
              `${params.value}${unit ? ` ${unit}` : ""}`,
            color: tokens.palette.ink,
            fontSize: 11,
            fontWeight: "bold",
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
        axisLabels.x || "类别",
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
