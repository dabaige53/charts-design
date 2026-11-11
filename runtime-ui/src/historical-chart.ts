// Read compatibility for historical native charts. New declarations use the 40 registered codes.
import { format } from "../../dashboard_runtime/web/engine.mjs";
import type { Config, Document } from "./types";
const types = new Set([
  "bar",
  "line",
  "area",
  "pie",
  "scatter",
  "heatmap",
  "funnel",
  "waterfall",
]);
export function historicalData(doc: Document, id: string) {
  const c = doc.manifest.components[id],
    groups: Config[] = doc.computed?.grouped?.[id] || [];
  return {
    headers: [
      doc.manifest.datasets[c.datasetId].fields[c.x].label || c.x,
      ...(c.series
        ? [
            doc.manifest.datasets[c.datasetId].fields[c.series].label ||
              c.series,
          ]
        : []),
      ...c.measures.map((mid: string) => doc.manifest.metrics[mid].label),
    ],
    rows: groups.map((g) => [
      g.x,
      ...(c.series ? [g.group] : []),
      ...c.measures.map((mid: string) => g.values[mid]),
    ]),
  };
}
export function historicalOption(
  doc: Document,
  id: string,
  palette: Config,
): Config {
  const c = doc.manifest.components[id],
    kind = c.chartType,
    rows: Config[] = doc.computed?.grouped?.[id] || [];
  if (!types.has(kind)) throw Error(`不支持的历史图表：${kind}`);
  const categories = [...new Set(rows.map((r) => r.x))],
    groups = [...new Set(rows.map((r) => r.group))],
    metrics = doc.manifest.metrics;
  const names = c.measures as string[],
    metric = metrics[names[0]];
  const base = {
    animation: false,
    color: [
      palette.primary,
      palette.secondary,
      palette.tertiary,
      palette.slate,
    ],
    grid: { left: 24, right: 24, top: 32, bottom: 32, containLabel: true },
    tooltip: { trigger: "axis", renderMode: "richText", confine: true },
    textStyle: { color: palette.ink },
  };
  if (!rows.length)
    return {
      ...base,
      xAxis: { show: false },
      yAxis: { show: false },
      series: [],
      graphic: [
        {
          type: "text",
          left: "center",
          top: "middle",
          style: { text: "当前筛选范围暂无数据", fill: palette.inkMuted },
        },
      ],
    };
  if (kind === "pie" || kind === "funnel")
    return {
      ...base,
      legend: { bottom: 0, type: "scroll" },
      tooltip: {
        ...base.tooltip,
        trigger: "item",
        formatter: (p: Config) =>
          `${String(p.name)}\n${metric.label} ${format(p.value, metric)}`,
      },
      series: [
        {
          type: kind,
          radius: kind === "pie" ? ["40%", "68%"] : undefined,
          top: kind === "funnel" ? 24 : undefined,
          bottom: 48,
          data: rows.map((r) => ({
            name: String(r.x),
            value: r.values[names[0]],
          })),
        },
      ],
    };
  if (kind === "scatter")
    return {
      ...base,
      legend: { top: 0, type: "scroll" },
      xAxis: {
        type: "value",
        name: doc.manifest.datasets[c.datasetId].fields[c.x].label || c.x,
      },
      yAxis: { type: "value", name: metric.unit || metric.label },
      tooltip: {
        ...base.tooltip,
        trigger: "item",
        formatter: (p: Config) =>
          `${String(p.seriesName)}\n${String(p.value[0])} / ${format(p.value[1], metric)}`,
      },
      series: groups.map((group) => ({
        name: group == null ? metric.label : String(group),
        type: "scatter",
        symbolSize: 10,
        data: rows
          .filter(
            (r) =>
              r.group === group && r.x != null && r.values[names[0]] != null,
          )
          .map((r) => [r.x, r.values[names[0]]]),
      })),
    };
  if (kind === "heatmap")
    return {
      ...base,
      legend: { show: false },
      xAxis: { type: "category", data: categories },
      yAxis: { type: "category", data: groups },
      visualMap: {
        min: Math.min(...rows.map((r) => r.values[names[0]] ?? 0)),
        max: Math.max(...rows.map((r) => r.values[names[0]] ?? 0)),
        bottom: 0,
        orient: "horizontal",
        inRange: { color: [palette.primarySoft, palette.primary] },
      },
      tooltip: {
        ...base.tooltip,
        trigger: "item",
        formatter: (p: Config) =>
          `${String(categories[p.value[0]])} · ${String(groups[p.value[1]])}\n${format(p.value[2], metric)}`,
      },
      series: [
        {
          type: "heatmap",
          data: rows
            .filter((r) => r.values[names[0]] != null)
            .map((r) => [
              categories.indexOf(r.x),
              groups.indexOf(r.group),
              r.values[names[0]],
            ]),
        },
      ],
    };
  if (kind === "waterfall") {
    let running = 0;
    const values = rows.map((row) => {
      const delta = row.values[names[0]];
      if (delta == null) return null;
      const value = {
        value: Math.abs(delta),
        base: Math.min(running, running + delta),
        itemStyle: { color: delta < 0 ? palette.negative : palette.primary },
      };
      running += delta;
      return value;
    });
    return {
      ...base,
      xAxis: { type: "category", data: categories },
      yAxis: { type: "value", name: metric.unit || "" },
      series: [
        {
          type: "bar",
          stack: "waterfall",
          itemStyle: { color: "transparent" },
          emphasis: { disabled: true },
          tooltip: { show: false },
          data: values.map((v) => v?.base ?? null),
        },
        {
          name: metric.label,
          type: "bar",
          stack: "waterfall",
          data: values.map((v) =>
            v ? { value: v.value, itemStyle: v.itemStyle } : null,
          ),
        },
      ],
    };
  }
  return {
    ...base,
    legend: { top: 0, type: "scroll" },
    xAxis: { type: "category", data: categories },
    yAxis: { type: "value", name: metric.unit || "" },
    series: names.flatMap((mid) =>
      groups.map((group) => ({
        name:
          groups.length > 1
            ? `${metrics[mid].label} · ${String(group)}`
            : metrics[mid].label,
        type: kind === "bar" ? "bar" : "line",
        ...(kind === "area" ? { areaStyle: { opacity: 0.16 } } : {}),
        barMaxWidth: 24,
        symbolSize: 8,
        data: categories.map(
          (category) =>
            rows.find((r) => r.x === category && r.group === group)?.values[
              mid
            ] ?? null,
        ),
      })),
    ),
  };
}
