import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";
import DOMPurify from "dompurify";
import { definitions } from "./charts";
import { encodingOption } from "./charts/encoding";
import { adaptOption } from "./charts/adaptive";
import { encodingTable } from "../../dashboard_runtime/web/encoding.mjs";
import { applyEChartsOptions } from "./echarts-options.mjs";
import type { Config, Document } from "./types";
export type ChartContext = { document: Document; id: string };
export const chartCodes = Object.keys(definitions);
export const palette = {
  primary: "#123B5D",
  primaryStrong: "#0B2A42",
  primarySoft: "#DCE8F0",
  secondary: "#2C6485",
  tertiary: "#628EA8",
  slate: "#8C9DAE",
  ink: "#17212B",
  inkMuted: "#52606D",
  inkSubtle: "#52606D",
  positive: "#A4453C",
  negative: "#2F6B55",
  attention: "#9A6A18",
  canvas: "#FFFFFF",
  surfaceGround: "#F8FAFC",
  gridline: "#E6EAED",
  rule: "#C9D1D8",
};
const colors = [
  palette.primary,
  palette.secondary,
  palette.tertiary,
  palette.slate,
  palette.attention,
  "#7867AD",
  "#634B36",
  "#BDD0DC",
];
const tokens = {
  palette,
  axisTitleStyleX: { fontSize: 11, color: palette.inkMuted },
  axisTitleStyleY: { fontSize: 11, color: palette.inkMuted },
  commonOption: {
    animation: false,
    color: colors,
    textStyle: {
      fontFamily: "Arial, PingFang SC, sans-serif",
      color: palette.ink,
    },
    grid: { top: 40, left: 48, right: 24, bottom: 40, containLabel: true },
    xAxis: {
      axisLine: { lineStyle: { color: palette.rule } },
      axisLabel: { color: palette.inkMuted },
    },
    yAxis: {
      axisLine: { show: false },
      axisLabel: { color: palette.inkMuted },
      splitLine: { lineStyle: { color: palette.gridline } },
    },
  },
};
const text = (value: any): string =>
  value == null
    ? "—"
    : Array.isArray(value)
      ? value.map(text).join(" / ")
      : typeof value === "object"
        ? JSON.stringify(value)
        : String(value);
// Canvas rich text avoids putting external category/series strings in an HTML tooltip.
function tooltip(params: any) {
  const points = Array.isArray(params) ? params : [params];
  return [
    text(points[0]?.axisValueLabel ?? points[0]?.name),
    ...points.map(
      (p) => `${p.seriesName ? text(p.seriesName) + "  " : ""}${text(p.value)}`,
    ),
  ].join("\n");
}
export function encodedOption(config: Config, context?: ChartContext): Config {
  if (!["r02", "c03", "r03", "k01", "f02"].includes(config.code))
    throw Error(`图表 ${config.code} 不支持当前动态编码`);
  if (!context) throw Error("动态编码图表需要绑定指标与字段说明。");
  return encodingOption(context.document, context.id, config.data.records);
}
export function chartOption(
  config: Config,
  grain = "month",
  context?: ChartContext,
): Config {
  const definition = definitions[config.code];
  if (!definition) throw Error(`未注册图表：${config.code}`);
  if (!config.data) throw Error(`图表 ${config.code} 缺少数据`);
  const preset = config.encoding
    ? encodedOption(config, context)
    : definition.optionBuilder(config.data, grain, tokens, config);
  const option = applyEChartsOptions(preset, config.echarts);
  const secureTooltip = (value: Config = {}) => {
    const formatter = value.formatter;
    // Keep each chart's fields, units and layout; sanitize the final HTML at its boundary.
    return {
      ...value,
      confine: true,
      ...(typeof formatter === "function"
        ? {
            formatter: (...args: any[]) =>
              DOMPurify.sanitize(String(formatter(...args))),
          }
        : !formatter
          ? { renderMode: "richText", formatter: tooltip }
          : {}),
    };
  };
  option.tooltip = Array.isArray(option.tooltip)
    ? option.tooltip.map(secureTooltip)
    : secureTooltip(option.tooltip);
  option.aria = { enabled: true, decal: { show: !!config.accessibleTexture } };
  return option;
}
export function chartData(
  config: Config,
  grain = "month",
  context?: ChartContext,
): { headers: string[]; rows: any[][] } {
  if (config.encoding) {
    if (!context) throw Error("动态数据表需要绑定指标与字段说明。");
    return encodingTable(context.document, context.id, config.data.records);
  }
  const definition = definitions[config.code];
  if (!definition?.tableDataExtractor) throw Error("当前图表没有数据表定义");
  return definition.tableDataExtractor(config.data, grain, config);
}
export function EChartSurface({
  option,
  label,
  className = "chart-body",
  onReady,
  onSelect,
  selectedName,
}: {
  option: Config;
  label: string;
  className?: string;
  onReady?: (chart: echarts.ECharts | undefined) => void;
  onSelect?: (point: Config) => void;
  selectedName?: string;
}) {
  const target = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  const currentOption = useRef(option);
  const selection = useRef(selectedName);
  selection.current = selectedName;
  const scheduleDraw = useRef<(() => void) | undefined>(undefined);
  currentOption.current = option;
  const callbacks = useRef({ onReady, onSelect });
  callbacks.current = { onReady, onSelect };
  useEffect(() => {
    if (!target.current) return;
    const chart = echarts.init(target.current, undefined, {
      renderer: "canvas",
    });
    callbacks.current.onReady?.(chart);
    chart.on("click", (point) => callbacks.current.onSelect?.(point));
    let frame = 0, width = 0, height = 0;
    let renderedOption: Config | undefined;
    let renderedSelection: string | undefined;
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let renderedReducedMotion = motion.matches;
    const draw = () => {
      frame = 0;
      const nextWidth = target.current?.clientWidth || 0;
      const nextHeight = target.current?.clientHeight || 0;
      if (!nextWidth || !nextHeight) return;
      const resized = nextWidth !== width || nextHeight !== height;
      const changed = renderedOption !== currentOption.current;
      const selectionChanged = renderedSelection !== selection.current;
      if (!resized && !changed && !selectionChanged && renderedReducedMotion === motion.matches) return;
      try {
        if (resized) chart.resize({ width: nextWidth, height: nextHeight, silent: true });
        const next = adaptOption(applyEChartsOptions(currentOption.current, {}), nextWidth, nextHeight);
        const list = (value: any): Config[] => value == null ? [] : Array.isArray(value) ? value : [value];
        next.animation = !motion.matches;
        next.animationDuration = 0;
        next.animationDurationUpdate = resized || motion.matches ? 0 : 260;
        next.animationEasingUpdate = "cubicOut";
        next.series = list(next.series).map((series, index) => {
          const axes = series.type === "bar"
            ? [...list(next.xAxis).slice(series.xAxisIndex ?? 0, (series.xAxisIndex ?? 0) + 1),
               ...list(next.yAxis).slice(series.yAxisIndex ?? 0, (series.yAxisIndex ?? 0) + 1)]
            : [];
          const categories = axes.find((axis) => axis.type === "category")?.data;
          return {
            ...series,
            id: series.id ?? `runtime:${index}:${series.type}:${series.name ?? ""}`,
            animation: !motion.matches,
            animationDuration: 0,
            animationDurationUpdate: next.animationDurationUpdate,
            animationEasingUpdate: "cubicOut",
            ...(Array.isArray(series.data) && categories ? {
              data: series.data.map((datum: any, at: number) => {
                const item = datum !== null && typeof datum === "object" && !Array.isArray(datum)
                  ? datum : { value: datum };
                const category = categories[at];
                const name = item.name ?? (category && typeof category === "object" ? category.value : category);
                const muted = selection.current != null && String(name) !== String(selection.current);
                return {
                  ...item,
                  name: String(name ?? at),
                  ...(muted ? {
                    itemStyle: { ...series.itemStyle, ...item.itemStyle, color: palette.rule, opacity: 0.55 },
                    emphasis: { ...item.emphasis, itemStyle: { ...item.emphasis?.itemStyle, color: palette.rule, opacity: 0.75 } },
                  } : {}),
                };
              }),
            } : {}),
          };
        });
        chart.setOption(next, {
          notMerge: false,
          replaceMerge: ["series", "xAxis", "yAxis", "grid", "dataset", "legend", "dataZoom", "visualMap", "graphic"],
          lazyUpdate: false,
          silent: true,
        });
        width = nextWidth;
        height = nextHeight;
        renderedOption = currentOption.current;
        renderedSelection = selection.current;
        renderedReducedMotion = motion.matches;
        setError("");
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(draw);
    };
    scheduleDraw.current = schedule;
    const observer = new ResizeObserver(schedule);
    motion.addEventListener("change", schedule);
    observer.observe(target.current);
    schedule();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      motion.removeEventListener("change", schedule);
      scheduleDraw.current = undefined;
      callbacks.current.onReady?.(undefined);
      chart.dispose();
    };
  }, []);
  useEffect(() => {
    scheduleDraw.current?.();
  }, [option, selectedName]);
  return (
    <>
      <div ref={target} className={className} role="img" aria-label={label} />
      {error && (
        <p role="alert" className="p-3 text-destructive">
          {error}
        </p>
      )}
    </>
  );
}
