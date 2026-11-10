import type { Config, Document, Filter } from "./types";

export function filterScope(document: Document, filters: Filter[], componentId?: string) {
  return filters
    .filter((filter) => !componentId || filter.componentIds.includes(componentId))
    .flatMap((filter) => {
      const date = Object.values(document.manifest.datasets)
        .some((dataset) => dataset.fields?.[filter.field]?.type === "date");
      const values = filter.values;
      if (!values.length && !date && filter.op !== "in") return [];
      return [{
        id: filter.id,
        label: filter.label,
        value: values.length
          ? values.join(filter.op === "range" ? " 至 " : "、")
          : date ? "全部日期" : "全部",
      }];
    });
}

export function ViewScope({
  document,
  filters,
  grains,
}: {
  document: Document;
  filters: Filter[];
  grains: Record<string, string>;
}) {
  const scope = filterScope(document, filters);
  const periods = [...new Set(Object.entries(document.manifest.components)
    .filter(([, component]) => component.config?.hasGranularity)
    .map(([id, component]) => grains[id] || component.config?.defaultGranularity || "month"))];
  const updated = document.snapshot.updatedAt;
  const periodLabels: Record<string, string> = { month: "月度", quarter: "季度" };
  const items: Config[] = [
    ...scope,
    ...(periods.length ? [{
      id: "granularity", label: "图表粒度",
      value: periods.map((period) => periodLabels[period] || period).join("、"),
    }] : []),
    ...(updated ? [{
      id: "updated", label: "数据更新",
      value: new Intl.DateTimeFormat("zh-CN", {
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", hour12: false,
      }).format(new Date(updated)),
    }] : []),
  ];
  if (!items.length && document.snapshot.status !== "fixture") return null;
  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs leading-5 text-muted-foreground" aria-label="当前统计范围" aria-live="polite">
      {document.snapshot.status === "fixture" && <span className="font-medium text-foreground">示例数据</span>}
      <dl className="flex flex-wrap gap-x-4 gap-y-1">
        {items.map((item) => (
          <div key={item.id} className="flex flex-wrap gap-x-1.5">
            <dt>{item.label}</dt><dd className="text-foreground">{item.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
