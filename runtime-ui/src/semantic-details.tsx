import { useEffect, useRef, useState } from "react";
import type { Config, Document, Filter, TableState } from "./types";
import { filterScope } from "./view-scope";
import { Calculator, Layers3, Table2, Database } from "lucide-react";
import { Table, TableHeader, TableHead, TableBody, TableRow, TableCell } from "./components/ui/table";
import { RecoveryAlert } from "./recovery-alert";

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
  if (metric.field && aggregations[metric.aggregation])
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

export function SemanticDetails({
  value, component, document, componentId, filters, onReadData,
}: {
  value: Config | null;
  component: Config;
  document: Document;
  componentId: string;
  filters: Filter[];
  onReadData?: (state: TableState) => Promise<Config>;
}) {
  if (!value) return null;
  const explanation = value.originalExplanation || component.config?.explanation || {};
  const presentation = value.originalPresentation || component.config?.presentation || component.presentation || {};
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
  const structure = explanation.structure || {};
  const category = component.binding?.categoryField || component.x;
  const categoryName = fields[category]?.label || category;
  const horizontal = component.config?.code === "c02";
  const measureNames = metrics.map((metric) => metric.label || metric.name || metric.id);
  const axes = [
    ["X 轴", structure.xAxis, presentation.axisLabels?.x],
    ["Y 轴", structure.yAxis, presentation.axisLabels?.y || presentation.axisLabels?.leftY],
    ["右侧 Y 轴", structure.rightYAxis, presentation.axisLabels?.rightY],
  ].map(([label, axis, fallback]) => {
    const name = fallback || axis?.name || (categoryName
      ? (label === (horizontal ? "Y 轴" : "X 轴") ? categoryName : label !== "右侧 Y 轴" ? measureNames.join("、") : undefined)
      : undefined);
    return [label, axis, name];
  }).filter(([, axis, fallback]) => axis || fallback);
  const series: Config[] = metricIds.length
    ? (presentation.seriesLabels || measureNames).map((name: string) => ({ name }))
    : structure.series || (presentation.seriesLabels || []).map((name: string) => ({ name }));
  const overview = component.subtitle || component.config?.desc || (!metricIds.length ? explanation.overview : undefined);
  const chart = (component.family || component.kind) === "chart";
  const specs: [string, unknown][] = [
    ["图表类型", explanation.type || ({ kpi: "指标卡", table: "数据表", chart: "分析图表" } as Record<string, string>)[component.family || component.kind]],
    ["统计周期", explanation.period],
    ["对比基准", explanation.comparison],
  ];
  return (
    <>
      {(overview || specs.some(([, text]) => text) || scope.length > 0) && (
        <section className="space-y-3">
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
      {chart && (axes.length > 0 || series.length > 0) && (
        <section className="space-y-3 border-t border-border pt-4">
          <h3 className="flex items-center gap-1.5 text-xs font-semibold text-brand">
            <Layers3 className="size-4" aria-hidden="true" />图表结构
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {axes.map(([label, axis, fallback]) => (
              <div key={label} className="space-y-1 text-xs">
                <p className="font-semibold text-brand">{label} · {fallback || axis?.name}</p>
                {axis?.meaning && <p className="mt-1 leading-relaxed text-muted-foreground">业务含义：{axis.meaning}</p>}
                {axis?.range && <p className="mt-1 text-muted-foreground">{label === "X 轴" ? "数据粒度" : "量纲刻度"}：{axis.range}</p>}
              </div>
            ))}
          </div>
          {series.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {series.map((item, index) => (
                <span key={`${item.name}-${index}`} className="inline-flex items-center gap-1.5 text-xs">
                  <span className="size-1.5 shrink-0 rounded-full bg-brand" aria-hidden="true" />
                  <span className="font-medium">{item.name}</span>
                  {item.desc && <span className="ml-1 text-muted-foreground">{item.desc}</span>}
                </span>
              ))}
            </div>
          )}
        </section>
      )}
      {shownMetrics.length > 0 && (
        <section className="space-y-3 border-t border-border pt-4">
          <h3 className="flex items-center gap-1.5 text-xs font-semibold text-brand">
            <Calculator className="size-4" aria-hidden="true" />指标说明
          </h3>
          <div className="divide-y divide-border">
            {shownMetrics.map((metric, index) => {
              const metricDataset = document.manifest.datasets[metric.datasetId] || dataset;
              const metricFields = metricDataset.fields || {};
              return (
                <div key={metric.id || index} className="space-y-2 py-3 first:pt-0 last:pb-0">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h4 className="text-xs font-semibold text-brand">{metric.label || metric.name || metric.id}</h4>
                  </div>
                  <DetailRows rows={[
                    ["业务定义", metric.definition || metric.businessDefinition || metric.description || "尚未提供业务定义"],
                    ["计算公式", calculation(metric, metricFields) || "尚未提供计算方式"],
                    ["汇总方式", aggregations[metric.aggregation] || metric.aggregation],
                    ["单位", metric.unit || (metric.format === "percent" ? "%" : undefined)],
                    ["展示方式", metric.format === "percent" ? "比例原值 × 100，以百分比显示" : undefined],
                    ["计算边界", ["ratio", "entity_ratio"].includes(metric.aggregation) ? "分母为零时不生成比例值。" : undefined],
                    ["判定规则", metric.rule],
                    ["复核状态", metric.status === "reviewed" ? "已复核" : metric.status ? "待复核" : undefined],
                  ]} />
                </div>
              );
            })}
          </div>
        </section>
      )}
      {component.kind === "table" && Object.keys(fields).length > 0 && (
        <section className="space-y-3 border-t border-border pt-4">
          <h3 className="text-xs font-semibold text-brand">表格字段</h3>
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
      {(source || datasetId) && (
        <section className="space-y-3 border-t border-border pt-4">
          <h3 className="flex items-center gap-1.5 text-xs font-semibold text-brand">
            <Database className="size-4" aria-hidden="true" />数据来源
          </h3>
          <DetailRows rows={[
            ["来源", source?.name || source?.label || sourceId],
            ["数据集", dataset.label || dataset.name || datasetId],
            ["数据性质", source?.kind === "fixture" ? "示例数据" : undefined],
          ]} />
          {(source?.sql || source?.query) && <pre className="overflow-x-auto whitespace-pre-wrap break-words bg-muted/40 p-3 text-xs leading-relaxed">{String(source.sql || source.query)}</pre>}
        </section>
      )}
      {!overview && !shownMetrics.length && !Object.keys(fields).length && !axes.length && !series.length && (
        <p className="text-sm text-muted-foreground">此组件尚未保存业务说明。</p>
      )}
      {onReadData && (
        <DetailData
          key={JSON.stringify([document.id, document.revision, document.dataVersion, componentId, filters])}
          fields={fields}
          onReadData={onReadData}
        />
      )}
    </>
  );
}

function DetailData({ fields, onReadData }: {
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
    <section className="space-y-3 border-t border-border pt-4" aria-label="明细数据" aria-busy={loading}>
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="flex items-center gap-1.5 text-xs font-semibold text-brand">
          <Table2 className="size-4 self-center" aria-hidden="true" />明细数据
        </h3>
        <span className="text-xs text-muted-foreground">示例 · 最多 10 行</span>
      </div>
      {error ? (
        <RecoveryAlert title="明细数据未能加载" message={error} onRetry={() => setAttempt((count) => count + 1)} busy={loading} />
      ) : (
        <div className="min-w-0">
          <Table aria-label="当前筛选范围的明细数据示例">
            <TableHeader>
              <TableRow>
                {keys.map((key) => <TableHead key={key} className={`whitespace-nowrap text-xs ${fields[key]?.type === "number" ? "text-right" : ""}`}>{fields[key]?.label || key}</TableHead>)}
              </TableRow>
            </TableHeader>
            <TableBody>
              {result?.rows?.length ? result.rows.map((row: Config, index: number) => (
                <TableRow key={index}>
                  {keys.map((key) => <TableCell key={key} className={`whitespace-nowrap text-xs tabular-nums ${fields[key]?.type === "number" ? "text-right" : ""}`}>
                    {row[key] == null ? "—" : typeof row[key] === "object" ? JSON.stringify(row[key]) : String(row[key])}
                  </TableCell>)}
                </TableRow>
              )) : <TableRow><TableCell colSpan={Math.max(1, keys.length)} className="py-6 text-center text-xs text-muted-foreground">{loading ? "正在读取示例数据…" : "当前筛选范围暂无数据"}</TableCell></TableRow>}
            </TableBody>
          </Table>
          {result && <p className="mt-2 text-xs text-muted-foreground">展示 {result.rows?.length ?? 0} 行，当前筛选共 {Number(result.totalRows ?? 0).toLocaleString()} 行</p>}
        </div>
      )}
    </section>
  );
}
