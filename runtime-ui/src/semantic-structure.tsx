import { useMemo, useState, useId } from "react";
import DOMPurify from "dompurify";
import type { Config } from "./types";

type Annotation = {
  id: string; anchor: [number, number]; label: [number, number];
  align?: "left" | "center" | "right";
  metricId?: string; name?: string; description?: string;
};
type StructureDiagram = {
  version: 1; viewBox: [number, number, number, number]; svg: string;
  annotations: Annotation[]; status?: "ready" | "stale";
};

/** Saved geometry, never reconstructed from chart type or filtered values. */
export function SemanticStructure({ diagram, metrics, compact = false }: {
  diagram?: StructureDiagram; metrics: Config; compact?: boolean;
}) {
  const [selected, setSelected] = useState("");
  const definitionId = useId();
  const image = useMemo(() => diagram ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(DOMPurify.sanitize(diagram.svg, {
    ALLOWED_TAGS: ["svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan", "title", "desc"],
    ALLOWED_ATTR: ["xmlns", "viewBox", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "width", "height", "d", "points", "fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "opacity", "fill-opacity", "stroke-opacity", "fill-rule", "transform", "font-size", "font-weight", "text-anchor", "dominant-baseline"],
    ALLOW_DATA_ATTR: false,
  }))}` : "", [diagram?.svg]);
  if (!diagram || diagram.status === "stale") return <p className="text-xs text-muted-foreground" role="status">
    {diagram ? "结构说明待更新" : "结构说明未配置"}
  </p>;
  const [, , width, height] = diagram.viewBox;
  const parts = diagram.annotations.map((item) => {
    const metric = item.metricId ? metrics[item.metricId] : undefined;
    return { ...item,
      name: item.metricId ? metric?.label || metric?.name || item.metricId : item.name,
      unit: item.metricId ? metric?.unit || (metric?.format === "percent" ? "%" : "") : "",
      description: item.metricId
        ? metric ? metric.definition || metric.businessDefinition || metric.description || "尚未提供业务定义。" : "关联指标已不存在，请更新结构说明。"
        : item.description || "尚未提供业务定义。",
    };
  });
  const active = parts.find((part) => part.id === selected);
  return <div className="space-y-3">
    <div className="semantic-diagram-container">
    <div className={`semantic-diagram${compact ? " semantic-diagram-compact" : ""}`} style={{ aspectRatio: `${width} / ${height}` }}>
      <img src={image} alt="图表结构示意" className="absolute inset-0 h-full w-full" />
      <svg viewBox={diagram.viewBox.join(" ")} className="absolute inset-0 pointer-events-none" aria-hidden="true">
        {parts.map((part) => {
          const [x, y] = part.label;
          const [ax, ay] = part.anchor;
          const elbow = (x + ax) / 2;
          return <g key={part.id} fill="none" stroke={selected === part.id ? "var(--foreground)" : "var(--muted-foreground)"} strokeWidth={selected === part.id ? 2 : 1}>
            <path d={`M${x} ${y}H${elbow}V${ay}H${ax}`} />
            <circle cx={ax} cy={ay} r="3" fill="var(--background)" />
          </g>;
        })}
      </svg>
      {parts.map((part) => <button key={part.id} type="button" className="semantic-callout"
        aria-pressed={selected === part.id} aria-expanded={selected === part.id}
        aria-controls={definitionId}
        onClick={() => setSelected((previous) => previous === part.id ? "" : part.id)}
        style={{ position: "absolute", left: `${part.label[0] / width * 100}%`, top: `${part.label[1] / height * 100}%`,
          transform: `translate(${part.align === "left" ? "0" : part.align === "right" ? "-100%" : "-50%"}, -50%)`,
          maxWidth: "26%", textAlign: part.align || "center" }}>
        {part.name}{part.unit && <span className="semantic-callout-unit"> {part.unit}</span>}
      </button>)}
    </div>
    </div>
    <div id={definitionId} aria-live="polite" aria-atomic="true">
      {active && <aside key={active.id} className="semantic-definition rounded-lg bg-muted/50 p-4 text-xs">
        <h4 className="font-semibold">{active.name}</h4>
        <p className="mt-2 leading-relaxed text-muted-foreground">{active.description}</p>
      </aside>}
    </div>
  </div>;
}
