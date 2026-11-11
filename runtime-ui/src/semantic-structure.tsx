import { useId, useMemo, useState, type CSSProperties } from "react";
import { EChartSurface } from "./chart";
import type { Config } from "./types";

type Axis = { label: string; name: string; description?: string };
type Part = { id: string; name: string; description: string; type?: string; axis?: number; stack?: string; color?: string };

/** A structural diagram uses declared encodings, never illustrative business values. */
export function SemanticStructure({ axes, series, metrics, option }: {
  axes: Axis[];
  series: Config[];
  metrics: Config[];
  option?: Config;
}) {
  const [selected, setSelected] = useState("");
  const hatch = useId().replace(/:/g, "");
  const nativeSeries: Config[] = option?.series || [];
  const cartesian = nativeSeries.length > 0
    && nativeSeries.every((item) => ["bar", "line"].includes(item.type))
    && !(option?.yAxis || []).some((axis: Config) => axis.type === "category");
  const parts: Part[] = (nativeSeries.length ? nativeSeries : series).map((item, index) => {
    const name = series[index]?.name || item.name || `系列 ${index + 1}`;
    const metric = metrics.find((candidate) => [candidate.label, candidate.name, candidate.id].includes(name));
    return {
      id: `series-${index}`, name, type: item.type, axis: item.yAxisIndex || 0, stack: item.stack,
      color: typeof (item.itemStyle?.color || item.lineStyle?.color || option?.color?.[index]) === "string"
        ? item.itemStyle?.color || item.lineStyle?.color || option?.color?.[index] : undefined,
      description: metric?.definition || metric?.businessDefinition || metric?.description
        || series[index]?.desc || series[index]?.description || "尚未提供业务定义。",
    };
  });
  const references: Part[] = nativeSeries.flatMap((item, index) => (item.markLine?.data || []).flatMap((mark: Config, position: number) =>
    !Array.isArray(mark) && mark.yAxis != null ? [{
      id: `reference-${index}-${position}`, name: mark.name || "参考线", type: "reference",
      axis: item.yAxisIndex || 0, description: mark.description || `参考值：${mark.yAxis}`,
    }] : []));
  const axisParts: Part[] = axes.map((axis, index) => ({
    id: `axis-${index}`, name: axis.name, description: axis.description || `${axis.label}表示${axis.name}。`,
  }));
  const allParts = [...axisParts, ...parts, ...references];
  const active = allParts.find((part) => part.id === selected);
  const preview = useMemo(() => option ? { ...option, animation: false } : undefined, [option]);
  const labels = [...parts, ...references];
  const height = Math.max(340, Math.ceil(labels.length / 2) * 70 + 160);
  const bars = parts.filter((part) => part.type === "bar");
  const groups = [...new Set(bars.map((part) => part.stack || part.id))];
  const barX = (part: Part) => 190 + groups.indexOf(part.stack || part.id) * (54 / groups.length);
  const barWidth = Math.max(2, Math.min(24, 54 / Math.max(1, groups.length) - 2));
  const toggle = (id: string) => setSelected((previous) => previous === id ? "" : id);
  const button = (part: Part, style?: CSSProperties) => (
    <button type="button" key={part.id} style={style} className="semantic-callout"
      aria-pressed={selected === part.id} onClick={() => toggle(part.id)}>
      {part.name}
    </button>
  );
  return (
    <div className="space-y-3">
      {!cartesian && <div className="flex flex-wrap justify-between gap-2">
        {axisParts.map((part) => button(part))}
      </div>}
      {cartesian ? (
        <div className="semantic-diagram" style={{ height }}>
          <svg viewBox={`0 0 600 ${height}`} preserveAspectRatio="none" role="img" aria-label="图表结构示意，不表示业务数值">
            <defs><pattern id={hatch} width="7" height="7" patternUnits="userSpaceOnUse">
              <path d="M0 7L7 0" stroke="currentColor" strokeWidth="1" />
            </pattern></defs>
            <path d={`M160 80V${height - 40}H440V80`} fill="none" stroke="var(--border)" />
            {bars.map((part, index) => [0, 1, 2].map((column) => {
              const stackIndex = part.stack ? bars.filter((other, previous) => previous < index && other.stack === part.stack).length : 0;
              const x = barX(part) + column * 85;
              const barHeight = Math.min(42 + column * 12, (height - 80) / Math.max(1, bars.length));
              return <rect key={`${part.id}-${column}`} x={x} y={height - 40 - barHeight * (stackIndex + 1)}
                width={barWidth} height={barHeight - 2}
                fill={part.color || (index % 2 ? `url(#${hatch})` : "currentColor")} opacity={index % 2 ? 0.7 : 0.85} />;
            }))}
            {parts.filter((part) => part.type === "line").map((part, index) => {
              const y = 75 + index * 24;
              return <g key={part.id} fill="var(--background)" stroke={part.color || "currentColor"} strokeWidth="2">
                <path d={`M215 ${y + 55}L300 ${y}L385 ${y + 22}`} fill="none" />
                {[[215, y + 55], [300, y], [385, y + 22]].map(([x, cy]) => <circle key={x} cx={x} cy={cy} r="4" />)}
              </g>;
            })}
            {references.map((part, index) => <path key={part.id} d={`M160 ${55 + index * 18}H440`}
              stroke="currentColor" opacity=".6" strokeDasharray="5 4" fill="none" />)}
            {labels.map((part, index) => {
              const left = index % 2 === 0;
              const y = 105 + Math.floor(index / 2) * 70;
              const barIndex = bars.indexOf(part);
              const lineIndex = parts.filter((item) => item.type === "line").indexOf(part);
              const endX = part.type === "bar" ? barX(part) + barWidth / 2 : part.type === "line" ? 300 : 420;
              const stackIndex = part.stack ? bars.filter((other, previous) => previous < barIndex && other.stack === part.stack).length : 0;
              const barHeight = Math.min(42, (height - 80) / Math.max(1, bars.length));
              const endY = part.type === "bar" ? height - 40 - barHeight * (stackIndex + .5) : part.type === "line" ? 75 + lineIndex * 24 : 55 + references.indexOf(part) * 18;
              return <g key={part.id} fill="none" stroke={selected === part.id ? "var(--foreground)" : "var(--muted-foreground)"} strokeWidth={selected === part.id ? 2 : 1}>
                <path d={`M${left ? 125 : 475} ${y}H${left ? 145 : 455}V${endY}H${endX}`} />
                <circle cx={endX} cy={endY} r="3" fill="var(--background)" />
              </g>;
            })}
            {axes.map((axis, index) => {
              const bottom = axis.label === "X 轴";
              const right = axis.label === "右侧 Y 轴";
              const x = bottom ? 300 : right ? 440 : 160;
              const y = bottom ? height - 40 : 80;
              return <g key={axis.label} fill="none" stroke={selected === `axis-${index}` ? "var(--foreground)" : "var(--muted-foreground)"}>
                <path d={bottom ? `M300 ${height - 18}V${y}` : `M${right ? 540 : 60} 42V60H${x}V${y}`} />
                <circle cx={x} cy={y} r="3" fill="var(--background)" />
              </g>;
            })}
          </svg>
          {axisParts.map((part, index) => button(part, axes[index].label === "X 轴"
            ? { position: "absolute", bottom: -20, left: "35%", width: "30%", textAlign: "center" }
            : { position: "absolute", top: 0, [axes[index].label === "右侧 Y 轴" ? "right" : "left"]: 0, maxWidth: "40%" }))}
          {labels.map((part, index) => button(part, {
            position: "absolute", top: 87 + Math.floor(index / 2) * 70,
            [index % 2 ? "right" : "left"]: 0, width: "21%",
          }))}
        </div>
      ) : (
        <>
          {preview && <div className="h-64"><EChartSurface option={preview} label="当前图形" className="h-full w-full" /></div>}
          <div className="flex flex-wrap gap-2">{labels.map((part) => button(part))}</div>
        </>
      )}
      {active && <aside className="rounded-lg bg-muted/50 p-4 text-xs" aria-live="polite" aria-atomic="true">
        <h4 className="font-semibold">{active.name}</h4>
        <p className="mt-2 leading-relaxed text-muted-foreground">{active.description}</p>
      </aside>}
    </div>
  );
}
