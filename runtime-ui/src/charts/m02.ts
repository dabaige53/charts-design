// Migrated from aefb7e857663a42a6bb426f8b5ba3eca48cb950e; business data comes through props.
import type { ChartDefinition } from "./types";
import type { Config } from "../types";
const definition: ChartDefinition = {
  code: "m02",
  optionBuilder: (d: any, gran: any, tokens: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const seriesLabels = presentation.seriesLabels || [];
    const tooltipLabels = presentation.tooltipValueLabels || seriesLabels;
    const units = presentation.units || [];
    const labels = presentation.labels || [];
    const domains = presentation.domains || {};
    const option: Config = {
      ...tokens.commonOption,
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(255, 255, 255, 0.98)",
        borderColor: tokens.palette.rule,
        borderWidth: 1,
        padding: [8, 12],
        extraCssText:
          "box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;",
      },
      legend: {
        top: 0,
        right: 12,
        orient: "horizontal",
        icon: "rect",
        itemWidth: 10,
        itemHeight: 10,
        itemGap: 12,
        data: ["乐观情景", "基准预测", "悲观情景"],
        textStyle: { fontSize: 10, color: tokens.palette.inkMuted },
      },
      xAxis: { type: "category", data: d.quarters, axisTick: { show: false } },
      yAxis: {
        type: "value",
        min: 6.0,
        max: 17.0,
        name: "客运营收 (亿元)",
        nameLocation: "end",
        nameTextStyle: tokens.axisTitleStyleY,
        axisLabel: { formatter: "{value} 亿" },
        splitLine: { lineStyle: { color: tokens.palette.gridline } },
      },
      series: [
        {
          name: "乐观情景",
          type: "line",
          data: d.optimistic,
          lineStyle: {
            color: tokens.palette.positive,
            width: 2,
            type: "dashed",
          },
          itemStyle: { color: tokens.palette.positive },
        },
        {
          name: "基准预测",
          type: "line",
          data: d.baseline,
          lineStyle: { color: tokens.palette.primary, width: 2.5 },
          itemStyle: {
            color: tokens.palette.primary,
            borderColor: "#FFF",
            borderWidth: 2,
          },
        },
        {
          name: "悲观情景",
          type: "line",
          data: d.pessimistic,
          lineStyle: {
            color: tokens.palette.negative,
            width: 2,
            type: "dashed",
          },
          itemStyle: { color: tokens.palette.negative },
        },
      ],
    };
    [
      ["x", option.xAxis],
      ["y", option.yAxis],
    ].forEach(([key, axisOption]: any) => {
      const domain = domains[key];
      [axisOption]
        .flat()
        .filter(Boolean)
        .forEach((axis: any, index: any) => {
          if (axisLabels[key]) axis.name = axisLabels[key];
          delete axis.min;
          delete axis.max;
          const axisDomain = Array.isArray(domain && domain[0])
            ? domain[index]
            : domain;
          if (Array.isArray(axisDomain)) [axis.min, axis.max] = axisDomain;
          if (axis.type === "value")
            axis.axisLabel = {
              ...(axis.axisLabel || {}),
              formatter: (value: any) =>
                `${value}${units[index] || units[0] || ""}`,
            };
        });
    });
    if (option.visualMap) {
      delete option.visualMap.min;
      delete option.visualMap.max;
      if (Array.isArray(domains.visualMap))
        [option.visualMap.min, option.visualMap.max] = domains.visualMap;
    }
    if (option.radar && Array.isArray(option.radar.indicator))
      option.radar.indicator = option.radar.indicator.map(
        (indicator: any, index: any) => {
          const configuredDomain = Array.isArray(domains.indicators)
            ? domains.indicators[index]
            : domains.value;
          const { min, max, ...semanticIndicator } = indicator;
          return {
            ...semanticIndicator,
            name: labels[index] || indicator.name,
            ...(Array.isArray(configuredDomain)
              ? { min: configuredDomain[0], max: configuredDomain[1] }
              : {}),
          };
        },
      );
    const thresholdValues = Object.values(presentation.thresholds || {}).filter(
      (value: any) => typeof value === "number",
    );
    const optionSeries = Array.isArray(option.series) ? option.series : [];
    optionSeries.forEach((series: any, index: any) => {
      if (seriesLabels[index]) series.name = seriesLabels[index];
      if (series.label && units[index])
        series.label.formatter = (params: any) =>
          `${params.value}${units[index]}`;
      if (series.type === "pie" && Array.isArray(series.data))
        series.data = series.data.map((item: any, itemIndex: any) => ({
          ...item,
          name: labels[itemIndex] || item.name,
        }));
      if (series.type === "radar" && Array.isArray(series.data))
        series.data = series.data.map((item: any, itemIndex: any) => ({
          ...item,
          name: seriesLabels[itemIndex] || item.name,
        }));
      if (series.type === "gauge") {
        delete series.min;
        delete series.max;
        if (Array.isArray(domains.value))
          [series.min, series.max] = domains.value;
        if (series.detail)
          series.detail.formatter = (value: any) => `${value}${units[0] || ""}`;
        if (Array.isArray(series.data) && series.data[0])
          series.data[0].name =
            tooltipLabels[0] || seriesLabels[0] || labels[0] || "";
      }
      if (series.markLine && thresholdValues.length)
        series.markLine.data = thresholdValues.map(
          (value: any, thresholdIndex: any) => {
            const original =
              (series.markLine.data && series.markLine.data[thresholdIndex]) ||
              {};
            const key = Object.prototype.hasOwnProperty.call(original, "xAxis")
              ? "xAxis"
              : "yAxis";
            return {
              ...original,
              [key]: value,
              label: {
                ...(original.label || {}),
                formatter:
                  labels[thresholdIndex] ||
                  `${value}${units[index] || units[0] || ""}`,
              },
            };
          },
        );
      if (!thresholdValues.length && series.markLine) delete series.markLine;
    });
    if (option.legend && seriesLabels.length) option.legend.data = seriesLabels;
    if (
      option.tooltip &&
      !["d02", "r02", "r03", "d04", "f02", "r04", "f03", "r05"].includes(
        cfg.code,
      )
    )
      option.tooltip.formatter = (params: any) => {
        const items = Array.isArray(params) ? params : [params];
        const heading =
          (items[0] && (items[0].axisValueLabel || items[0].name)) || "";
        return `${heading ? `<div class="font-bold text-primary-strong mb-1">${heading}</div>` : ""}${items.map((item: any, index: any) => `<div class="flex items-center justify-between gap-4 py-0.5"><span class="text-ink-muted">${tooltipLabels[index] || seriesLabels[index] || item.seriesName || "数值"}:</span><span class="font-mono font-bold text-primary">${item.value}${units[index] || units[0] || ""}</span></div>`).join("")}`;
      };
    return option;
  },
  tableDataExtractor: (d: any, gran: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const seriesLabels = presentation.seriesLabels || [];
    const tooltipLabels = presentation.tooltipValueLabels || seriesLabels;
    const units = presentation.units || [];
    const labels = presentation.labels || [];
    const thresholds = presentation.thresholds || {};
    const totals = presentation.totals || {};
    const table = {
      headers: [
        "预测周期",
        "悲观情景 (亿元)",
        "基准预测 (亿元)",
        "乐观情景 (亿元)",
      ],
      rows: d.quarters.map((q: any, i: any) => [
        q,
        `¥${d.pessimistic[i]} 亿`,
        `¥${d.baseline[i]} 亿`,
        `¥${d.optimistic[i]} 亿`,
      ]),
    };
    const configuredHeaders = presentation.tableHeaders || [
      axisLabels.y || axisLabels.x,
      ...(tooltipLabels.length ? tooltipLabels : seriesLabels),
    ];
    table.headers = table.headers.map(
      (header: any, index: any) => configuredHeaders[index] || header,
    );
    table.rows = table.rows.map((row: any) =>
      row.map((value: any, index: any) => {
        if (!units[index - 1] || index === 0 || typeof value !== "string")
          return value;
        const numeric = value.match(/[+-]?(?:[0-9]+[.]?[0-9]*|[.][0-9]+)/);
        return numeric ? `${numeric[0]} ${units[index - 1]}`.trim() : value;
      }),
    );
    return table;
  },
};
export default definition;
