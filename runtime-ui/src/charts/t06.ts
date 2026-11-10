// Migrated from aefb7e857663a42a6bb426f8b5ba3eca48cb950e; business data comes through props.
import type { ChartDefinition } from "./types";
const definition: ChartDefinition = {
  code: "t06",
  hasGranularity: true,
  defaultGranularity: "month",
  optionBuilder: (d: any, gran: any, tokens: any, cfg: any = {}) => {
    const cur = d[gran] || d.month;
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const seriesLabels = presentation.seriesLabels || ["主指标", "变化率"];
    const tooltipLabels = presentation.tooltipValueLabels || seriesLabels;
    const units = presentation.units || [cfg.unit || "", "%"];
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
        formatter: (params: any) => {
          let res = `<div class="font-bold text-primary-strong mb-1">${params[0].name}</div>`;
          res += `<div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">${tooltipLabels[0]}:</span><span class="font-mono font-bold text-ink">${params[0].value}${units[0] ? ` ${units[0]}` : ""}</span></div>`;
          if (params[1]) {
            res += `<div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">${tooltipLabels[1]}:</span><span class="font-mono font-bold text-positive">${params[1].value}${units[1] ? ` ${units[1]}` : ""}</span></div>`;
          }
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
      xAxis: {
        type: "category",
        name: axisLabels.x || "周期",
        nameLocation: "middle",
        nameGap: 20,
        nameTextStyle: tokens.axisTitleStyleX,
        data: cur.categories,
        axisTick: { show: false },
      },
      yAxis: [
        {
          type: "value",
          name: axisLabels.leftY || seriesLabels[0],
          nameLocation: "end",
          nameTextStyle: tokens.axisTitleStyleY,
          axisLabel: {
            formatter: (value: any) =>
              `${value}${units[0] ? ` ${units[0]}` : ""}`,
          },
          splitLine: { lineStyle: { color: tokens.palette.gridline } },
        },
        {
          type: "value",
          name: axisLabels.rightY || seriesLabels[1],
          nameLocation: "end",
          nameTextStyle: {
            color: tokens.palette.inkSubtle,
            fontSize: 10,
            align: "right",
            padding: [0, 0, 6, 0],
          },
          axisLabel: { formatter: (value: any) => `${value}${units[1] || ""}` },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: seriesLabels[0],
          type: "bar",
          barWidth: gran === "month" ? 14 : 26,
          data: cur.revenue,
          itemStyle: { color: tokens.palette.primary },
        },
        {
          name: seriesLabels[1],
          type: "line",
          yAxisIndex: 1,
          data: cur.yieldGrowth,
          lineStyle: { color: tokens.palette.positive, width: 2.5 },
          itemStyle: {
            color: tokens.palette.positive,
            borderColor: "#FFF",
            borderWidth: 2,
          },
          symbolSize: 6,
          label: {
            show: true,
            position: "top",
            distance: 6,
            formatter: (params: any) =>
              params.value == null
                ? "—"
                : `${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(params.value)}${units[1] || ""}`,
            color: tokens.palette.positive,
            fontSize: 10,
            fontWeight: "bold",
          },
        },
      ],
    };
  },
  tableDataExtractor: (d: any, gran: any, cfg: any = {}) => {
    const cur = d[gran] || d.month;
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const seriesLabels = presentation.seriesLabels || ["主指标", "变化率"];
    const units = presentation.units || [cfg.unit || "", "%"];
    return {
      headers: presentation.tableHeaders || [
        axisLabels.x || "周期",
        `${seriesLabels[0]}${units[0] ? ` (${units[0]})` : ""}`,
        `${seriesLabels[1]}${units[1] ? ` (${units[1]})` : ""}`,
      ],
      rows: cur.categories.map((c: any, i: any) => [
        c,
        `${cur.revenue[i]}${units[0] ? ` ${units[0]}` : ""}`,
        `${cur.yieldGrowth[i]}${units[1] ? ` ${units[1]}` : ""}`,
      ]),
    };
  },
};
export default definition;
