import { memo, useLayoutEffect, useMemo, useRef, type ReactNode } from "react";
import { AlertTriangle, Trophy, TrendingUp, TrendingDown } from "lucide-react";
import { EChartSurface, palette } from "./chart";
import type { Config } from "./types";
const number = (v: any) =>
  typeof v === "number"
    ? v
    : typeof v === "string"
      ? Number.parseFloat(v.replaceAll(",", ""))
      : NaN;
const shown = (v: any) => (v == null || v === "" ? "—" : String(v));
const clamp = (n: number) => Math.max(0, Math.min(100, n));
function AnimatedValue({ value }: { value: any }) {
  const label = shown(value);
  const node = useRef<HTMLSpanElement>(null);
  const previous = useRef(label);
  const displayed = useRef<number | undefined>(undefined);
  useLayoutEffect(() => {
    const element = node.current!;
    const parse = (text: string) => text.match(/^([+-]?[\d,]+(?:\.\d+)?)(.*)$/);
    const before = parse(previous.current), after = parse(label);
    previous.current = label;
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    const finish = () => {
      cancelAnimationFrame(frame);
      element.textContent = label;
      displayed.current = after ? Number(after[1].replaceAll(",", "")) : undefined;
    };
    if (!before || !after || before[2] !== after[2] || motion.matches) {
      finish();
      return;
    }
    const from = displayed.current ?? Number(before[1].replaceAll(",", ""));
    const to = Number(after[1].replaceAll(",", ""));
    if (!Number.isFinite(from) || !Number.isFinite(to) || from === to) {
      finish();
      return;
    }
    const decimals = after[1].split(".")[1]?.length ?? 0;
    const formatter = new Intl.NumberFormat("en-US", {
      useGrouping: after[1].includes(","),
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
    const started = performance.now();
    const paint = (current: number) => {
      element.textContent = `${after[1].startsWith("+") && current >= 0 ? "+" : ""}${formatter.format(current)}${after[2]}`;
    };
    paint(from);
    const tick = (now: number) => {
      const progress = Math.min(1, (now - started) / 260);
      const current = from + (to - from) * (1 - (1 - progress) ** 3);
      displayed.current = current;
      paint(current);
      if (progress < 1) frame = requestAnimationFrame(tick);
      else finish();
    };
    frame = requestAnimationFrame(tick);
    motion.addEventListener("change", finish);
    return () => {
      cancelAnimationFrame(frame);
      motion.removeEventListener("change", finish);
    };
  }, [label]);
  return <span><span className="sr-only">{label}</span><span ref={node} aria-hidden="true">{label}</span></span>;
}
function Meter({ value, label }: { value: number; label: string }) {
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      {...(Number.isFinite(value)
        ? { "aria-valuenow": value }
        : { "aria-valuetext": "无数据" })}
      className="metric-meter w-full bg-[#dce8f0]"
    >
      <div
        className="h-full bg-[#123b5d]"
        style={{ width: Number.isFinite(value) ? clamp(value) + "%" : "0%" }}
      />
    </div>
  );
}
function Ring({ value, semi = false }: { value: number; semi?: boolean }) {
  const length = semi ? Math.PI * 38 : 2 * Math.PI * 38;
  return (
    <svg
      viewBox={semi ? "0 0 100 62" : "0 0 100 100"}
      className={semi ? "metric-ring metric-ring-semi shrink-0" : "metric-ring shrink-0"}
      role="img"
      aria-label={Number.isFinite(value) ? `完成 ${value}%` : "无完成度数据"}
    >
      {semi ? (
        <>
          <path
            d="M12 50 A38 38 0 0 1 88 50"
            fill="none"
            stroke="#dce8f0"
            strokeWidth="9"
          />
          <path
            d="M12 50 A38 38 0 0 1 88 50"
            fill="none"
            stroke="#123b5d"
            strokeWidth="9"
            strokeDasharray={`${(length * (Number.isFinite(value) ? clamp(value) : 0)) / 100} ${length}`}
          />
        </>
      ) : (
        <>
          <circle
            cx="50"
            cy="50"
            r="38"
            fill="none"
            stroke="#dce8f0"
            strokeWidth="9"
          />
          <circle
            cx="50"
            cy="50"
            r="38"
            fill="none"
            stroke="#123b5d"
            strokeWidth="9"
            strokeDasharray={`${(length * (Number.isFinite(value) ? clamp(value) : 0)) / 100} ${length}`}
            transform="rotate(-90 50 50)"
          />
          <text x="50" y="55" textAnchor="middle" fontSize="16" fill="#333">
            {Number.isFinite(value) ? Math.round(value) + "%" : "—"}
          </text>
        </>
      )}
    </svg>
  );
}
function FitMetricContent({ children }: { children: ReactNode }) {
  const viewport = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const host = viewport.current!, body = content.current!;
    let frame = 0;
    const fit = () => {
      const width = host.clientWidth, height = host.clientHeight;
      if (!width || !height) return;
      const scale = Math.max(0.875, Math.min(1.5, width / 280));
      host.style.setProperty("--metric-scale", String(scale));
      const bodyHeight = body.offsetHeight;
      if (bodyHeight > height)
        host.style.setProperty("--metric-scale", String(Math.max(0.875, scale * height / bodyHeight)));
    };
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(fit);
    });
    observer.observe(host);
    fit();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [children]);
  return (
    <div ref={viewport} className="relative flex min-h-0 min-w-0 flex-1 flex-col justify-center">
      <div
        ref={content}
        className="metric-content flex w-full min-w-0 flex-col break-words"
      >
        {children}
      </div>
    </div>
  );
}
export const MetricCard = memo(function MetricCard({ config }: { config: Config }) {
  const c = config,
    type = c.type || "mc01",
    percent = number(c.percent);
  if (!/^mc(?:0[1-9]|1[0-6])$/.test(type)) throw Error(`未注册指标卡：${type}`);
  const detailLabel = c.subLabel || c.gaugeSub || c.trendLabel || c.statusBadge;
  const detail =
    detailLabel && c.subVal != null && c.subVal !== ""
      ? `${detailLabel} ${c.subVal}`
      : (detailLabel ?? c.subVal);
  const spark = useMemo(
    () => ({
      animation: false,
      grid: { left: 2, right: 2, top: 8, bottom: 3 },
      xAxis: { type: "category", data: c.sparkMonths, show: false },
      yAxis: { type: "value", show: false },
      tooltip: {
        trigger: "axis",
        renderMode: "html",
        appendTo: document.body,
        confine: false,
        extraCssText: "z-index: 10000;",
        formatter: (points: any[]) => {
          const content = document.createElement("div");
          content.textContent = points.map((point) => `${point.axisValueLabel ?? point.name}：${point.value}`).join(" · ");
          return content;
        },
      },
      series: [
        {
          type: type === "mc12" ? "bar" : "line",
          data: c.sparkData || c.sparkline || [],
          barMaxWidth: 18,
          symbolSize: 8,
          smooth: false,
          lineStyle: { width: 2, color: palette.primary },
          itemStyle: { color: palette.primary },
          ...(type === "mc03" ? { areaStyle: { opacity: 0.1 } } : {}),
        },
      ],
    }),
    [type, c.sparkMonths, c.sparkData, c.sparkline],
  );
  const delta = (label: string, value: any) => (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      {number(value) > 0 ? (
        <TrendingUp size={14} />
      ) : number(value) < 0 ? (
        <TrendingDown size={14} />
      ) : null}
      {label} {shown(value)}
    </span>
  );
  return (
    <FitMetricContent>
      {type === "mc08" && (
        <div className="flex items-center gap-2 text-xs font-medium">
          <AlertTriangle size={18} className="text-[#9a6a18]" />
          {shown(c.alertLabel)}
        </div>
      )}
      {type === "mc07" && (
        <div className="flex items-center gap-2">
          <Trophy size={20} />
          <span className="border border-border px-2 py-1 text-xs">
            {shown(c.rankBadge)}
          </span>
        </div>
      )}
      {type === "mc06" ? (
        <div className="grid grid-cols-2 gap-5">
          <div>
            <p className="mb-2 text-xs text-muted-foreground">{c.leftTitle}</p>
            <p className="text-2xl font-semibold text-brand">
              <AnimatedValue value={c.leftVal} />
            </p>
            {c.leftYoy && delta("同比", c.leftYoy)}
          </div>
          <div>
            <p className="mb-2 text-xs text-muted-foreground">{c.rightTitle}</p>
            <p className="text-2xl font-semibold text-brand">
              <AnimatedValue value={c.rightVal} />
            </p>
            {c.rightYoy && delta("同比", c.rightYoy)}
          </div>
        </div>
      ) : type !== "mc15" || c.value != null ? (
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="min-w-0">
            {type === "mc10" && (
              <p className="mb-1 text-xs text-muted-foreground">
                {c.valueLabel || "中位数"}
              </p>
            )}
            <p
              className={
                type === "mc16" ? "metric-value metric-hero" : "metric-value"
              }
            >
              <AnimatedValue value={c.value} />
            </p>
            {detail && !["mc09", "mc10", "mc15"].includes(type) && (
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                {detail}
              </p>
            )}
          </div>
          {type === "mc05" && <Ring value={percent} semi />}
          {type === "mc11" && <Ring value={percent} />}
        </div>
      ) : null}
      {["mc01", "mc02", "mc14", "mc16", "mc12"].includes(type) && (
        <div className="flex flex-wrap gap-4">
          {c.yoy != null &&
            delta(type === "mc14" ? c.deltaLabel || "较基期" : "同比", c.yoy)}
          {type === "mc02" && c.mom != null && delta("环比", c.mom)}
        </div>
      )}
      {type === "mc04" && (
        <Meter value={percent} label={c.label || "目标完成度"} />
      )}
      {(type === "mc03" || type === "mc12") && (
        <EChartSurface
          option={spark}
          label={c.label || "近期走势"}
          className="metric-sparkline min-h-0 w-full"
        />
      )}
      {type === "mc09" && (
        <>
          <div className="flex h-3 gap-0.5">
            <div className="bg-[#123b5d]" style={{ width: c.segLeftWidth }} />
            <div className="bg-[#628ea8]" style={{ width: c.segRightWidth }} />
          </div>
          <div className="flex justify-between gap-3 text-xs">
            <span>{c.subLabel}</span>
            <span>{c.subVal}</span>
          </div>
        </>
      )}
      {type === "mc10" && c.stats && (
        <>
          <svg
            viewBox="0 0 280 40"
            className="h-10 w-full"
            role="img"
            aria-label={`最小 ${c.stats.min}，P25 ${c.stats.p25}，中位数 ${c.stats.median}，P75 ${c.stats.p75}，最大 ${c.stats.max}`}
          >
            <line x1="10" x2="270" y1="20" y2="20" stroke="#52606d" />
            <line x1="10" x2="10" y1="12" y2="28" stroke="#52606d" />
            <line x1="270" x2="270" y1="12" y2="28" stroke="#52606d" />
            <rect
              x={
                10 +
                (260 * (c.stats.p25 - c.stats.min)) /
                  (c.stats.max - c.stats.min || 1)
              }
              y="9"
              width={
                (260 * (c.stats.p75 - c.stats.p25)) /
                (c.stats.max - c.stats.min || 1)
              }
              height="22"
              fill="#dce8f0"
              stroke="#123b5d"
            />
            <line
              x1={
                10 +
                (260 * (c.stats.median - c.stats.min)) /
                  (c.stats.max - c.stats.min || 1)
              }
              x2={
                10 +
                (260 * (c.stats.median - c.stats.min)) /
                  (c.stats.max - c.stats.min || 1)
              }
              y1="9"
              y2="31"
              stroke="#123b5d"
              strokeWidth="2"
            />
          </svg>
          <p className="text-xs text-muted-foreground">
            {c.meanText} · {c.sampleText}
          </p>
        </>
      )}
      {type === "mc13" && <Bullet config={c} />}
      {type === "mc14" && (
        <div className="flex flex-col gap-2">
          {[
            [c.currentLabel || "本期", c.currentValue],
            [c.priorLabel || "基期", c.priorValue],
          ].map(([label, value], i) => (
            <div
              key={String(label)}
              className="grid grid-cols-[auto_1fr_auto] items-center gap-3 text-xs"
            >
              <span>{label}</span>
              <div className="h-2 bg-muted">
                <div
                  className={i ? "h-2 bg-[#628ea8]" : "h-2 bg-[#123b5d]"}
                  style={{
                    width: Number.isFinite(number(value))
                      ? (100 * number(value)) /
                          Math.max(
                            number(c.currentValue) || 0,
                            number(c.priorValue) || 0,
                            1,
                          ) +
                        "%"
                      : "0%",
                  }}
                />
              </div>
              <span>
                {shown(value)} {c.unit}
              </span>
            </div>
          ))}
        </div>
      )}
      {type === "mc15" && (
        <ul className="flex flex-col gap-2">
          {(c.items || []).map((item: Config) => (
            <li
              key={item.label}
              className="flex justify-between gap-3 border-b border-border pb-2 text-xs"
            >
              <span>{item.label}</span>
              <span>
                {item.value} {item.delta}
              </span>
            </li>
          ))}
        </ul>
      )}
      {type === "mc16" && c.note && (
        <p className="text-xs leading-relaxed text-muted-foreground">
          {c.note}
        </p>
      )}
      {type === "mc07" && c.rankSub && (
        <p className="text-xs text-muted-foreground">{c.rankSub}</p>
      )}
      {type === "mc06" && detail && (
        <p className="text-xs leading-5 text-muted-foreground">{detail}</p>
      )}
    </FitMetricContent>
  );
});
function Bullet({ config: c }: { config: Config }) {
  const max =
    number(c.max) ||
    Math.max(number(c.actual) || 0, number(c.target) || 0) * 1.2 ||
    1;
  const target = number(c.target),
    actual = number(c.actual);
  const ranges = (c.ranges || []).map((n: number) =>
    c.rangeBasis === "target" ? n * target : n,
  );
  return (
    <div className="flex flex-col gap-2">
      <div className="relative h-6 bg-[#dce8f0]">
        {ranges.map((n: number, i: number) => (
          <span
            key={i}
            className="absolute inset-y-0 left-0"
            style={{
              width: Math.min(100, (n / max) * 100) + "%",
              background: i ? "#c9d1d8" : "#e6eaed",
              zIndex: 3 - i,
            }}
          />
        ))}
        <span
          className="absolute left-0 top-2 z-10 h-2 bg-[#123b5d]"
          style={{ width: Math.min(100, ((actual || 0) / max) * 100) + "%" }}
        />
        {Number.isFinite(target) && (
          <span
            className="absolute inset-y-0 z-20 w-0.5 bg-[#17212b]"
            style={{ left: Math.min(100, (target / max) * 100) + "%" }}
          />
        )}
      </div>
      <p className="flex justify-between gap-2 text-xs text-muted-foreground">
        <span>
          实际 {shown(c.actual)} {c.unit}
        </span>
        <span>
          目标 {shown(c.target)} {c.unit}
        </span>
      </p>
    </div>
  );
}
