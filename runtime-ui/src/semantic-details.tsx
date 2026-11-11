import { useEffect, useId, useRef, useState } from "react";
import type { Config, Document, Filter, TableState } from "./types";
import { filterScope } from "./view-scope";
import { ArrowRight, ChevronDown } from "lucide-react";
import { Table, TableHeader, TableHead, TableBody, TableRow, TableCell } from "./components/ui/table";
import { RecoveryAlert } from "./recovery-alert";
import { SemanticStructure } from "./semantic-structure";

const aggregations: Record<string, string> = {
  sum: "求和", avg: "平均值", min: "最小值", max: "最大值",
  count: "记录条数", ratio: "分别汇总后相除", entity_ratio: "按实体汇总后计数并相除",
  unique: "唯一属性值",
};
const fieldTypes: Record<string, string> = {
  date: "日期", string: "文本", number: "数值", boolean: "是／否",
};

function calculation(metric: Config, fields: Config) {
  if (metric.formula || metric.calculation) return metric.formula || metric.calculation;
  const label = (field: string) => fields[field]?.label || field;
  if (metric.aggregation === "count") return "当前统计范围内的记录条数";
  if (metric.aggregation === "ratio")
    return `${label(metric.numerator)}合计 ÷ ${label(metric.denominator)}合计`;
  if (metric.aggregation === "entity_ratio")
    return `按${label(metric.entityField)}分别汇总，${label(metric.numerator)}合计大于零的实体数 ÷ ${label(metric.denominator)}合计大于零的实体数`;
  if (metric.field && ["sum", "avg", "min", "max", "unique"].includes(metric.aggregation))
    return `${label(metric.field)}${({ sum: "合计", avg: "平均值", min: "最小值", max: "最大值", unique: "唯一属性值" } as Record<string, string>)[metric.aggregation]}`;
  return undefined;
}

function DetailRows({ rows }: { rows: [string, unknown][] }) {
  return (
    <dl className="space-y-1.5">
      {rows.filter(([, value]) => value != null && value !== "").map(([label, value]) => (
        <div key={label} className="grid grid-cols-[4rem_minmax(0,1fr)] items-baseline gap-2 text-xs">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="min-w-0 break-words leading-relaxed">
            {label === "计算公式"
              ? <code className="box-decoration-clone rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[11.5px]">{String(value)}</code>
              : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function MetricDefinition({ metric, fields, scope, period }: {
  metric: Config; fields: Config; scope: { label: string; value: string }[]; period?: string;
}) {
  const ratio = ["ratio", "entity_ratio"].includes(metric.aggregation);
  const percent = metric.format === "percent";
  const decimals = metric.decimals ?? 2;
  const fieldLabel = (field: string) => fields[field]?.label || field;
  const formula = calculation(metric, fields);
  const unit = metric.unit || (percent ? "%" : "未配置单位");
  return <details className="semantic-metric" open>
    <summary>
      <h4>{metric.label || metric.name || metric.id || "未命名指标"}</h4>
      <span className="flex items-center gap-2 text-muted-foreground">{unit}<ChevronDown className="size-3.5" /></span>
    </summary>
    <dl className="semantic-metric-fields">
      <div className="semantic-wide"><dt>业务定义</dt><dd>
        {metric.definition || metric.businessDefinition || metric.description || "尚未提供业务定义"}
        {metric.status && <span className="ml-2 text-muted-foreground">{metric.status === "reviewed" ? "已复核" : "待复核"}</span>}
      </dd></div>
      <div className="semantic-wide"><dt>统计范围</dt><dd className="flex flex-wrap gap-1.5">
        {period && <span className="semantic-tag">{period}</span>}
        {scope.map((item, index) => <span className="semantic-tag" key={`${item.label}-${index}`}>{item.label}：{item.value}</span>)}
        {!scope.length && <span className="semantic-tag">当前数据集 · 未附加筛选</span>}
        {metric.scope && <span className="semantic-tag">{String(metric.scope)}</span>}
      </dd></div>
      <div className="semantic-wide"><dt>计算公式</dt><dd className="semantic-formula">
        {metric.aggregation === "ratio" && !metric.formula && !metric.calculation
          ? <span className="inline-flex flex-col text-center">
            <span className="border-b border-muted-foreground px-3 py-1">{fieldLabel(metric.numerator)}合计</span>
            <span className="px-3 py-1">{fieldLabel(metric.denominator)}合计</span>
          </span>
          : formula || "尚未提供计算方式"}
      </dd></div>
      <div className="semantic-wide"><dt>汇总方式</dt><dd className="flex flex-wrap items-center gap-2">
        {ratio ? <><span>{metric.aggregation === "entity_ratio" ? "按实体汇总并计数" : "分子、分母分别求和"}</span><ArrowRight className="size-3.5 text-muted-foreground" /><span>相除</span></>
          : aggregations[metric.aggregation] || metric.aggregation || "未配置"}
      </dd></div>
      <div><dt>数值显示</dt><dd>
        <div className="flex flex-wrap items-baseline gap-2 tabular-nums">
          {percent && <><span className="text-muted-foreground">0.15</span><ArrowRight className="size-3.5 text-muted-foreground" /></>}
          <span className="text-lg font-medium">{new Intl.NumberFormat("zh-CN", {
            minimumFractionDigits: decimals, maximumFractionDigits: decimals,
          }).format(percent ? 15 : 1234.5)}{percent ? "%" : ""}</span>
          {!percent && <span className="text-muted-foreground">{unit}</span>}
        </div>
        <p className="mt-1 text-[11px] text-muted-foreground">格式预览 · {decimals} 位小数{percent ? " · 原值 × 100" : ""}</p>
        {metric.displayScale && <p className="text-muted-foreground">显示换算：{String(metric.displayScale)}</p>}
      </dd></div>
      <div><dt>计算边界</dt><dd className="space-y-1">
        {ratio && <div className="flex justify-between gap-3 border-b border-border pb-1"><span>分母为零</span><span>不生成比例值</span></div>}
        {metric.rule ? <p>{String(metric.rule)}</p> : <div className="flex justify-between gap-3"><span>其他规则</span><span className="text-muted-foreground">未配置</span></div>}
      </dd></div>
    </dl>
  </details>;
}

export function SemanticDetails({
  value, component, document, componentId, filters, onReadData, grain,
}: {
  value: Config | null;
  component: Config;
  document: Document;
  componentId: string;
  filters: Filter[];
  onReadData?: (state: TableState) => Promise<Config>;
  grain?: string;
}) {
  const prefix = useId();
  const root = useRef<HTMLDivElement>(null);
  const [activeSection, setActiveSection] = useState("");
  if (!value) return null;
  const explanation = value.originalExplanation || component.config?.explanation || {};
  const presentation = (component.kind === "legacy" ? component.config?.presentation : component.presentation) || {};
  const datasetId = component.datasetId || component.binding?.datasetId;
  const dataset = document.manifest.datasets[datasetId] || value.dataset || {};
  const fields: Config = dataset.fields || {};
  const sources = (document.manifest as Config).sources || {};
  const sourceId = dataset.sourceId || component.sourceId;
  const source = sources[sourceId];
  const scope = filterScope(document, filters, componentId);
  const metricIds = [...new Set([
    ...(component.measures || []),
    ...Object.values(component.binding?.measures || {}),
  ])] as string[];
  const bound = Object.fromEntries(metricIds
    .filter((id) => document.manifest.metrics[id])
    .map((id) => [id, document.manifest.metrics[id]]));
  const declarations = metricIds.length ? bound : value.metrics || {};
  const metrics: Config[] = Object.entries(declarations).map(([id, metric]) => ({ id, ...(metric as Config) }));
  const originalMetrics: Config[] = explanation.metrics || [];
  // Current metric declarations remain the authority for bound data.
  const shownMetrics = metricIds.length ? metrics : metrics.length ? metrics : originalMetrics;
  const overview = component.subtitle || component.config?.desc || (!metricIds.length ? explanation.overview : undefined);
  const specs: [string, unknown][] = [
    ["统计周期", explanation.period],
    ["对比基准", explanation.comparison],
  ];
  const sections = [
    ["structure", "图表结构"],
    ...(shownMetrics.length ? [["metrics", "指标口径"]] : []),
    ...(component.kind === "table" && Object.keys(fields).length ? [["fields", "表格字段"]] : []),
    ...(onReadData ? [["data", "明细数据"]] : []),
    ...(source || datasetId ? [["source", "数据来源"]] : []),
  ];
  return (
    <div ref={root} className="semantic-details">
      {sections.length > 0 && <nav className="semantic-nav" aria-label="详情章节">
        {sections.map(([key, label]) => <a key={key} href={`#${prefix}-${key}`}
          aria-current={(activeSection || sections[0][0]) === key ? "location" : undefined}
          onClick={(event) => {
            event.preventDefault();
            setActiveSection(key);
            const target = Array.from(root.current?.querySelectorAll<HTMLElement>("section[id]") || [])
              .find((section) => section.id === `${prefix}-${key}`);
            if (target) target.style.scrollMarginTop = `${(root.current?.querySelector("nav")?.clientHeight || 48) + 12}px`;
            target?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
          }}>{label}</a>)}
      </nav>}
      {(overview || specs.some(([, text]) => text) || scope.length > 0) && (
        <section className="space-y-3 py-4">
          {overview && <p className="text-sm leading-relaxed text-foreground">{overview}</p>}
          {(specs.some(([, text]) => text) || scope.length > 0) && (
            <dl className="flex flex-wrap gap-x-5 gap-y-2 text-xs">
              {[...specs, ...scope.map((item): [string, unknown] => [item.label, item.value])]
                .filter(([, text]) => text != null && text !== "")
                .map(([label, text]) => (
                  <div key={label} className="flex items-baseline gap-1.5">
                    <dt className="text-muted-foreground">{label}：</dt>
                    <dd>{String(text)}</dd>
                  </div>
                ))}
            </dl>
          )}
        </section>
      )}
      <section id={`${prefix}-structure`} className="semantic-section">
        <h3>图表结构</h3>
        <SemanticStructure diagram={presentation.structureDiagram} metrics={document.manifest.metrics} />
      </section>
      {shownMetrics.length > 0 && (
        <section id={`${prefix}-metrics`} className="semantic-section">
          <h3>指标口径</h3>
          {shownMetrics.map((metric, index) => <MetricDefinition key={metric.id || index}
            metric={metric} fields={(document.manifest.datasets[metric.datasetId] || dataset).fields || {}}
            scope={scope} period={grain ? ({ month: "月度", quarter: "季度" } as Record<string, string>)[grain] || grain : explanation.period} />)}
        </section>
      )}
      {component.kind === "table" && Object.keys(fields).length > 0 && (
        <section id={`${prefix}-fields`} className="semantic-section">
          <h3>表格字段</h3>
          <div className="divide-y divide-border">
            {Object.entries(fields).map(([id, field]) => {
              const declaration = field as Config;
              const column = component.config?.columns?.find((item: Config) => item.key === id)
                || component.presentation?.columns?.find((item: Config) => item.key === id);
              const fieldMetric = Object.values(document.manifest.metrics).find((metric: Config) =>
                metric.datasetId === datasetId && metric.field === id && metric.unit) as Config | undefined;
              return (
                <div key={id} className="space-y-2 py-3">
                  <h4 className="text-sm font-medium">{declaration.label || id}</h4>
                  <DetailRows rows={[
                    ["字段类型", fieldTypes[declaration.type] || declaration.type],
                    ["业务说明", declaration.description || declaration.definition || column?.description],
                    ["单位", declaration.unit || column?.unit || fieldMetric?.unit],
                    ["计算方式", declaration.formula || column?.formula],
                  ]} />
                </div>
              );
            })}
          </div>
        </section>
      )}
      {onReadData && (
        <DetailData
          sectionId={`${prefix}-data`}
          key={JSON.stringify([document.id, document.revision, document.dataVersion, componentId, filters])}
          fields={fields}
          onReadData={onReadData}
        />
      )}
      {(source || datasetId) && (
        <section id={`${prefix}-source`} className="semantic-section">
          <h3>数据来源</h3>
          <DetailRows rows={[
            ["来源", source?.name || source?.label || sourceId],
            ["数据集", dataset.label || dataset.name || datasetId],
            ["数据性质", source?.kind === "fixture" ? "示例数据" : undefined],
          ]} />
          {(source?.sql || source?.query) && <pre className="overflow-x-auto whitespace-pre-wrap break-words bg-muted/40 p-3 text-xs leading-relaxed">{String(source.sql || source.query)}</pre>}
        </section>
      )}
      {!overview && !shownMetrics.length && !Object.keys(fields).length && !presentation.structureDiagram && (
        <p className="text-sm text-muted-foreground">此组件尚未保存业务说明。</p>
      )}

    </div>
  );
}

function DetailData({ fields, onReadData, sectionId }: {
  sectionId: string;
  fields: Config;
  onReadData: (state: TableState) => Promise<Config>;
}) {
  const [result, setResult] = useState<Config | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const reader = useRef(onReadData);
  reader.current = onReadData;
  useEffect(() => {
    let live = true;
    setLoading(true);
    setError("");
    void reader.current({ page: 1, pageSize: 10 }).then((data) => {
      if (live) setResult(data);
    }).catch((cause) => {
      if (live) setError(cause instanceof Error ? cause.message : String(cause));
    }).finally(() => {
      if (live) setLoading(false);
    });
    return () => { live = false; };
  }, [attempt]);
  const keys = Object.keys(fields).length ? Object.keys(fields) : Object.keys(result?.rows?.[0] || {});
  return (
    <section id={sectionId} className="semantic-section" aria-label="明细数据" aria-busy={loading}>
      <div className="flex items-baseline justify-between gap-3">
        <h3>明细数据</h3>
        <span className="text-xs text-muted-foreground">最多 10 行</span>
      </div>
      {error ? (
        <RecoveryAlert title="明细数据未能加载" message={error} onRetry={() => setAttempt((count) => count + 1)} busy={loading} />
      ) : (
        <div className="min-w-0">
          <Table aria-label="当前筛选范围的明细数据">
            <TableHeader>
              <TableRow>
                {keys.map((key) => <TableHead key={key} className="whitespace-nowrap text-center text-xs">{fields[key]?.label || key}</TableHead>)}
              </TableRow>
            </TableHeader>
            <TableBody>
              {result?.rows?.length ? result.rows.map((row: Config, index: number) => (
                <TableRow key={index}>
                  {keys.map((key) => <TableCell key={key} className="whitespace-nowrap text-center text-xs tabular-nums">
                    {row[key] == null ? "—" : typeof row[key] === "object" ? JSON.stringify(row[key]) : String(row[key])}
                  </TableCell>)}
                </TableRow>
              )) : <TableRow><TableCell colSpan={Math.max(1, keys.length)} className="py-6 text-center text-xs text-muted-foreground">{loading ? "正在读取明细数据…" : "当前筛选范围暂无数据"}</TableCell></TableRow>}
            </TableBody>
          </Table>
          {result && <p className="mt-2 text-xs text-muted-foreground">展示 {result.rows?.length ?? 0} 行，当前筛选共 {Number(result.totalRows ?? 0).toLocaleString()} 行</p>}
        </div>
      )}
    </section>
  );
}
