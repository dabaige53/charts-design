// Migrated from aefb7e857663a42a6bb426f8b5ba3eca48cb950e; business data comes through props.
import type { ChartDefinition } from "./types";
import type { Config } from "../types";
const definition: ChartDefinition = {
  code: "k06",
  optionBuilder: (d: any, gran: any, tokens: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const axisLabels = presentation.axisLabels || {};
    const seriesLabels = presentation.seriesLabels || [];
    const tooltipLabels = presentation.tooltipValueLabels || seriesLabels;
    const units = presentation.units || [];
    const labels = presentation.labels || [];
    const domains = presentation.domains || {};
    const option: Config = {
      tooltip: {
        backgroundColor: "rgba(255, 255, 255, 0.98)",
        borderColor: tokens.palette.rule,
        borderWidth: 1,
        padding: [8, 12],
        extraCssText:
          "box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;",
        formatter: "{b}: {c}% 航网体量",
      },
      series: [
        {
          type: "sunburst",
          radius: ["15%", "85%"],
          center: ["50%", "52%"],
          data: d.hierarchy,
          label: { rotate: "radial", fontSize: 10, color: "#FFF" },
          itemStyle: { borderColor: "#FFF", borderWidth: 2 },
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
      headers: ["父级", "节点", "层级", "数值"],
      rows: (() => {
        const rows: any[][] = [];
        const visit = (nodes: any, parent: any = "", depth: any = 0) =>
          nodes.forEach((node: any) => {
            if (Array.isArray(node.children) && node.children.length)
              visit(node.children, node.name, depth + 1);
            else rows.push([parent, node.name, depth, node.value]);
          });
        visit(d.hierarchy);
        return rows;
      })(),
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
