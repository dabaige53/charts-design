import type { Config, Document, Filter } from "./types";
import { filterScope } from "./view-scope";
import { Calculator, Layers3 } from "lucide-react";

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
    <dl className="space-y-2">
      {rows.filter(([, value]) => value != null && value !== "").map(([label, value]) => (
        <div key={label} className="grid gap-1 text-sm sm:grid-cols-[5rem_minmax(0,1fr)] sm:gap-3">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="break-words leading-6">{String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function SemanticDetails({
  value, component, document, componentId, filters,
}: {
  value: Config | null;
  component: Config;
  document: Document;
  componentId: string;
  filters: Filter[];
}) {
  if (!value) return null;
  const explanation = value.originalExplanation || component.config?.explanation || {};
  const presentation = value.originalPresentation || component.config?.presentation || component.presentation || {};
  const datasetId = component.datasetId || component.binding?.datasetId;
  const dataset = value.dataset || document.manifest.datasets[datasetId] || {};
  const fields: Config = dataset.fields || {};
  const sources = (document.manifest as Config).sources || {};
  const sourceId = dataset.sourceId || component.sourceId;
  const source = sources[sourceId];
  const scope = filterScope(document, filters, componentId);
  const metricIds = (component.measures || Object.values(component.binding?.measures || {})) as string[];
  const declarations = value.metrics ?? Object.fromEntries(metricIds.map((id) => [id, document.manifest.metrics[id]]));
  const metrics: Config[] = Object.entries(declarations).map(([id, metric]) => ({ id, ...(metric as Config) }));
  const originalMetrics: Config[] = explanation.metrics || [];
  // Current metric declarations remain the authority for bound data.
  const shownMetrics = metrics.length ? metrics : originalMetrics;
  const structure = explanation.structure || {};
  const axes = [
    ["X 轴", structure.xAxis, presentation.axisLabels?.x],
    ["Y 轴", structure.yAxis, presentation.axisLabels?.y || presentation.axisLabels?.leftY],
    ["右侧 Y 轴", structure.rightYAxis, presentation.axisLabels?.rightY],
  ].filter(([, axis, fallback]) => axis || fallback);
  const series: Config[] = structure.series || (presentation.seriesLabels || []).map((name: string) => ({ name }));
  const overview = explanation.overview || component.subtitle || component.config?.desc;
  const specs: [string, unknown][] = [
    ["图表类型", explanation.type],
    ["统计周期", explanation.period],
    ["对比基准", explanation.comparison],
  ];
  return (
    <>
      {(overview || specs.some(([, text]) => text) || scope.length > 0) && (
        <section className="space-y-3 rounded-lg border border-border bg-muted/40 px-4 py-3">
          {overview && <p className="text-sm leading-6">{overview}</p>}
          {(specs.some(([, text]) => text) || scope.length > 0) && (
            <dl className="flex flex-wrap gap-2 border-t border-dashed border-border pt-3 text-xs">
              {[...specs, ...scope.map((item): [string, unknown] => [item.label, item.value])]
                .filter(([, text]) => text != null && text !== "")
                .map(([label, text]) => (
                  <div key={label} className="flex items-center gap-1 rounded border border-border bg-card px-2 py-1">
                    <dt className="text-muted-foreground">{label}：</dt>
                    <dd>{String(text)}</dd>
                  </div>
                ))}
            </dl>
          )}
        </section>
      )}
      {(axes.length > 0 || series.length > 0) && (
        <section className="space-y-3 rounded-lg border border-border p-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-brand">
            <Layers3 className="size-4" aria-hidden="true" />坐标维度与数据序列
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {axes.map(([label, axis, fallback]) => (
              <div key={label} className="rounded-md bg-muted/50 px-4 py-3 text-sm">
                <p className="font-medium">{label} · {axis?.name || fallback}</p>
                {axis?.meaning && <p className="mt-1 leading-6 text-muted-foreground">{axis.meaning}</p>}
                {axis?.range && <p className="mt-1 text-muted-foreground">范围：{axis.range}</p>}
              </div>
            ))}
          </div>
          {series.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {series.map((item, index) => (
                <span key={`${item.name}-${index}`} className="rounded border border-border bg-muted/30 px-2 py-1 text-xs">
                  <span className="font-medium">{item.name}</span>
                  {item.desc && <span className="ml-1 text-muted-foreground">{item.desc}</span>}
                </span>
              ))}
            </div>
          )}
        </section>
      )}
      {shownMetrics.length > 0 && (
        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-brand">
            <Calculator className="size-4" aria-hidden="true" />指标口径与计算方式
          </h3>
          <div className="space-y-2">
            {shownMetrics.map((metric, index) => {
              const metricDataset = document.manifest.datasets[metric.datasetId] || dataset;
              const metricFields = metricDataset.fields || {};
              const metricSourceId = metricDataset.sourceId || sourceId;
              const metricSource = sources[metricSourceId];
              return (
                <div key={metric.id || index} className="space-y-3 rounded-lg border border-border px-4 py-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h4 className="text-sm font-semibold">{metric.name || metric.label || metric.id}</h4>
                    {metric.status && <span className="text-xs text-muted-foreground">{metric.status === "reviewed" ? "已复核" : "待复核"}</span>}
                  </div>
                  <DetailRows rows={[
                    ["业务定义", metric.definition || metric.businessDefinition || metric.description || "尚未提供业务定义"],
                    ["计算公式", calculation(metric, metricFields) || "尚未提供计算方式"],
                    ["汇总方式", aggregations[metric.aggregation] || metric.aggregation],
                    ["单位", metric.unit || (metric.format === "percent" ? "%" : undefined)],
                    ["展示方式", metric.format === "percent" ? "比例原值 × 100，以百分比显示" : undefined],
                    ["计算边界", ["ratio", "entity_ratio"].includes(metric.aggregation) ? "分母为零时不生成比例值。" : undefined],
                    ["判定规则", metric.rule],
                    ["数据来源", metricSource?.name || metricSource?.label || metricSourceId],
                  ]} />
                </div>
              );
            })}
          </div>
        </section>
      )}
      {component.kind === "table" && Object.keys(fields).length > 0 && (
        <section className="space-y-3">
          <h3 className="text-sm font-semibold text-brand">表格字段</h3>
          <div className="divide-y divide-border rounded-md border border-border">
            {Object.entries(fields).map(([id, field]) => {
              const declaration = field as Config;
              const column = component.config?.columns?.find((item: Config) => item.key === id)
                || component.presentation?.columns?.find((item: Config) => item.key === id);
              const fieldMetric = Object.values(document.manifest.metrics).find((metric: Config) =>
                metric.datasetId === datasetId && metric.field === id && metric.unit) as Config | undefined;
              return (
                <div key={id} className="space-y-2 px-4 py-3">
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
        <section className="space-y-3">
          <h3 className="text-sm font-semibold text-brand">数据来源</h3>
          <DetailRows rows={[
            ["来源", source?.name || source?.label || sourceId],
            ["数据集", dataset.label || dataset.name || datasetId],
            ["数据性质", source?.kind === "fixture" ? "示例数据" : undefined],
          ]} />
        </section>
      )}
      {!overview && !shownMetrics.length && !Object.keys(fields).length && !axes.length && !series.length && (
        <p className="text-sm text-muted-foreground">此组件尚未保存业务说明。</p>
      )}
      <details className="border-t border-border pt-3 text-sm">
        <summary className="cursor-pointer font-medium">查看字段、绑定及原始定义</summary>
        <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/50 p-3 text-xs leading-5">{JSON.stringify(value, null, 2)}</pre>
      </details>
    </>
  );
}
