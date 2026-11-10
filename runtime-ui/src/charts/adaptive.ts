// Preserved chart behavior migrated from aefb7e857663a42a6bb426f8b5ba3eca48cb950e.
/* Width-aware presentation fixes applied after every original option builder.
 *
 * The 40 original builders were tuned for wide two-column cards. Layout
 * templates now place charts in 4-, 6-, 8- and 12-column cells and on phones,
 * so each option is adjusted to its actual canvas width. Adjustments only
 * trigger when content would not fit, and never change data or series. */
let context: any = null;
export function textWidth(text: any, size: any = 12, weight: any = "normal") {
  const value: any = String(text ?? "");
  if (!context && typeof document !== "undefined")
    context = document.createElement("canvas").getContext("2d");
  if (!context)
    return [...value].reduce(
      (sum: any, ch: any) => sum + (ch.charCodeAt(0) > 255 ? size : size * 0.6),
      0,
    );
  context.font = `${weight} ${size}px Inter, "PingFang SC", "Segoe UI", sans-serif`;
  return context.measureText(value).width;
}
const list: any = (value: any) =>
  value == null ? [] : Array.isArray(value) ? value : [value];
function margin(value: any, width: any, fallback: any) {
  if (typeof value === "number") return value;
  if (typeof value === "string" && value.endsWith("%"))
    return (width * parseFloat(value)) / 100;
  if (typeof value === "string" && Number.isFinite(Number(value)))
    return Number(value);
  return fallback;
}
function label(value: any) {
  return value && typeof value === "object"
    ? (value.value ?? value.name ?? "")
    : value;
}
export function widthBucket(width: any) {
  return width < 400 ? "xs" : width < 560 ? "sm" : width < 760 ? "md" : "lg";
}
function scalePresentation(option: any, scale: number) {
  const text = (value: any) => {
    if (!value || typeof value !== "object") return;
    if (Array.isArray(value)) {
      value.forEach(text);
      return;
    }
    for (const [key, child] of Object.entries(value)) {
      if (["data", "source", "dataset", "value", "values", "coords", "points", "links", "records"].includes(key)) continue;
      if (key === "fontSize" && typeof child === "number")
        value[key] = Math.max(8, Math.round(child * scale));
      else if (key === "lineHeight" && typeof child === "number")
        value[key] = Math.max(10, Math.round(child * scale));
      else if (key === "font" && typeof child === "string")
        value[key] = child.replace(/(\d+(?:\.\d+)?)px/g, (_, size) => `${Math.max(8, Math.round(Number(size) * scale))}px`);
      else text(child);
    }
  };
  option.textStyle = { fontSize: 12, ...option.textStyle };
  for (const axis of [...list(option.xAxis), ...list(option.yAxis)]) {
    axis.axisLabel = { fontSize: 12, ...axis.axisLabel };
    axis.nameTextStyle = { fontSize: 12, ...axis.nameTextStyle };
    axis.nameGap = (axis.nameGap ?? 15) * scale;
    if (axis.type === "category")
      axis.axisLabel = { width: null, overflow: "none", rotate: 0, hideOverlap: false, ...axis.axisLabel };
  }
  for (const legend of list(option.legend)) {
    legend.textStyle = { fontSize: 12, ...legend.textStyle };
    legend.type ||= "plain";
    legend.itemWidth = (legend.itemWidth ?? 25) * scale;
    legend.itemHeight = (legend.itemHeight ?? 14) * scale;
    legend.itemGap = (legend.itemGap ?? 10) * scale;
  }
  for (const series of list(option.series)) {
    if (series.label) series.label = { fontSize: 12, ...series.label };
    for (const point of list(series.data)) {
      if (point && typeof point === "object") {
        text(point.label);
        text(point.textStyle);
      }
    }
    for (const key of ["barWidth", "barMaxWidth", "barMinWidth"])
      if (typeof series[key] === "number") series[key] = Math.max(1, series[key] * scale);
    if (typeof series.symbolSize === "number")
      series.symbolSize = Math.max(2, series.symbolSize * scale);
    if (typeof series.lineStyle?.width === "number")
      series.lineStyle.width = Math.max(1, series.lineStyle.width * scale);
  }
  text(option);
  for (const grid of list(option.grid))
    for (const side of ["left", "right", "top", "bottom"])
      if (typeof grid[side] === "number") grid[side] *= scale;
}
export function adaptOption(option: any, width: any, height = 320) {
  if (!option || typeof option !== "object" || !(width > 0)) return option;
  scalePresentation(option, Math.max(0.4, Math.min(2.5, width / 560, height / 320)));
  const grids: any = list(option.grid),
    xAxes: any = list(option.xAxis);
  // Ordered flow nodes wrap into a readable snake on narrower cards.
  for (const series of list(option.series))
    if (
      series?.type === "graph" &&
      series.layout === "none" &&
      series.data?.length
    ) {
      const columns: any = Math.max(
          1,
          Math.min(series.data.length, Math.floor(width / 190)),
        ),
        rows: any = Math.ceil(series.data.length / columns);
      for (const [i, item] of series.data.entries()) {
        const row: any = Math.floor(i / columns),
          col: any = i % columns;
        item.x = (row % 2 ? columns - 1 - col : col) * 210;
        item.y = row * 160;
        item.symbolSize = [Math.min(150, width - 36), 100];
      }
      Object.assign(series, {
        left: columns === 1 ? "50%" : 82,
        right: columns === 1 ? "50%" : 82,
        top: rows === 1 ? "45%" : 65,
        bottom: rows === 1 ? "45%" : 65,
      });
    }
  // 1. Legacy containLabel contains tick labels but not axis names: an x-axis
  //    name at the end is clipped by the canvas unless the right margin fits it.
  for (const axis of xAxes) {
    if (
      !axis ||
      !axis.name ||
      axis.show === false ||
      !["end", "max", undefined].includes(axis.nameLocation)
    )
      continue;
    const grid: any = grids[axis.gridIndex || 0];
    if (!grid || grid.containLabel !== true) continue;
    const style: any = axis.nameTextStyle || {};
    const need: any = Math.ceil(
      textWidth(axis.name, style.fontSize || 12, style.fontWeight || "normal") +
        (axis.nameGap ?? 15) +
        6,
    );
    if (margin(grid.right, width, width * 0.1) < need) grid.right = need;
  }
  // 2. Crowded category labels truncate (or rotate on very narrow slots) instead of overlapping.
  if (!option.dataZoom)
    for (const axis of xAxes) {
      if (
        !axis ||
        axis.type !== "category" ||
        !Array.isArray(axis.data) ||
        !axis.data.length ||
        axis.axisLabel?.rotate
      )
        continue;
      const grid: any = grids[axis.gridIndex || 0] || {};
      const plot: any = Math.max(
        80,
        width -
          margin(grid.left, width, width * 0.1) -
          margin(grid.right, width, width * 0.1),
      );
      const slot: any = plot / axis.data.length,
        size: any = axis.axisLabel?.fontSize || 12;
      const longest: any = Math.max(
        ...axis.data.map((item: any) => textWidth(label(item), size)),
      );
      if (longest <= slot - 6) continue;
      const next: any = { ...(axis.axisLabel || {}) };
      if (slot >= 44)
        Object.assign(next, {
          width: Math.floor(slot - 6),
          overflow: "truncate",
        });
      else
        Object.assign(next, {
          rotate: 30,
          width: 72,
          overflow: "truncate",
          hideOverlap: true,
          interval: "auto",
        });
      axis.axisLabel = next;
    }
  // 3. Legends that cannot fit on one line scroll instead of covering the plot.
  for (const legend of list(option.legend)) {
    if (
      !legend ||
      legend.show === false ||
      legend.type === "scroll" ||
      legend.orient === "vertical"
    )
      continue;
    const series: any = list(option.series);
    const names: any =
      legend.data?.map((item: any) =>
        typeof item === "object" ? item?.name : item,
      ) ||
      (series.length === 1 && ["pie", "funnel"].includes(series[0]?.type)
        ? list(series[0].data).map((item: any) => item?.name)
        : series.map((item: any) => item?.name)
      ).filter(Boolean);
    const size: any = legend.textStyle?.fontSize || 12;
    const total: any = names.reduce(
      (sum: any, name: any) =>
        sum +
        textWidth(name, size) +
        (legend.itemWidth ?? 25) +
        (legend.itemGap ?? 10) +
        5,
      0,
    );
    if (total > width - 24)
      Object.assign(legend, {
        type: "scroll",
        pageIconSize: 10,
        pageTextStyle: { fontSize: 10 },
      });
  }
  // 4. Value labels on narrow canvases hide when they would overlap.
  if (width < 560)
    for (const series of list(option.series))
      if (series?.label?.show && !series.labelLayout)
        series.labelLayout = { hideOverlap: true };
  return option;
}
