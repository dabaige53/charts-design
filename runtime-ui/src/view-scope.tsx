import type { Document, Filter } from "./types";

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
