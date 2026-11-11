// Migrated from aefb7e857663a42a6bb426f8b5ba3eca48cb950e; business data comes through props.
import type { ChartDefinition } from "./types";
const definition: ChartDefinition = {
  code: "t05",
  optionBuilder: (d: any, gran: any, tokens: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const seriesLabels =
      presentation.seriesLabels || d.lines.map((line: any) => line.name);
    const tooltipLabel = (presentation.tooltipValueLabels || ["数值"])[0];
    const unit = (presentation.units || [cfg.unit || ""])[0];
    return {
      ...tokens.commonOption,
      tooltip: {
        trigger: "item",
        backgroundColor: "rgba(255, 255, 255, 0.98)",
        borderColor: tokens.palette.rule,
        borderWidth: 1,
        padding: [8, 12],
        extraCssText:
          "box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;",
        formatter: (params: any) =>
          `<div class="font-bold text-primary-strong mb-1">${params.seriesName}</div><div class="flex items-center justify-between gap-4"><span class="text-ink-muted">${tooltipLabel} · ${d.stages[params.dataIndex]}:</span><span class="font-mono font-bold text-primary">${params.value}${unit ? ` ${unit}` : ""}</span></div>`,
      },
      xAxis: {
        type: "category",
        name: axisLabels.x || "阶段",
        data: d.stages,
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        name: axisLabels.y || `${tooltipLabel}${unit ? ` (${unit})` : ""}`,
        nameLocation: "end",
        nameTextStyle: tokens.axisTitleStyleY,
        axisLabel: { formatter: (value: any) => `${value}${unit || ""}` },
        splitLine: { lineStyle: { color: tokens.palette.gridline } },
      },
      series: d.lines.map((l: any, index: any) => ({
        name: seriesLabels[index] || l.name,
        type: "line",
        data: l.data,
        lineStyle: { color: l.color, width: 2.5 },
        itemStyle: { color: l.color, borderColor: "#FFF", borderWidth: 2 },
        label: {
          show: true,
          position: "top",
          formatter: (params: any) => `${params.value}${unit || ""}`,
          color: tokens.palette.ink,
          fontSize: 10,
          fontWeight: 600,
        },
      })),
    };
  },
  tableDataExtractor: (d: any, gran: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const seriesLabels =
      presentation.seriesLabels || d.lines.map((line: any) => line.name);
    const unit = (presentation.units || [cfg.unit || ""])[0];
    return {
      headers: presentation.tableHeaders || [
        axisLabels.y || "系列",
        ...d.stages,
      ],
      rows: d.lines.map((line: any, index: any) => [
        seriesLabels[index] || line.name,
        ...line.data.map((value: any) => `${value}${unit ? ` ${unit}` : ""}`),
      ]),
    };
  },
};
export default definition;
