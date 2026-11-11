// Migrated from aefb7e857663a42a6bb426f8b5ba3eca48cb950e; business data comes through props.
import type { ChartDefinition } from "./types";
const definition: ChartDefinition = {
  code: "k01",
  optionBuilder: (d: any, gran: any, tokens: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const tooltipLabel = (presentation.tooltipValueLabels || ["占比"])[0];
    const unit = (presentation.units || [cfg.unit || "%"])[0];
    return {
      tooltip: {
        trigger: "item",
        backgroundColor: "rgba(255, 255, 255, 0.98)",
        borderColor: tokens.palette.rule,
        borderWidth: 1,
        padding: [8, 12],
        extraCssText:
          "box-shadow: 0 4px 14px rgba(18, 59, 93, 0.08); border-radius: 6px;",
        formatter: (params: any) =>
          `${params.name}<br>${tooltipLabel}: ${params.value}${unit ? ` ${unit}` : ""}`,
      },
      series: [
        {
          type: "pie",
          radius: ["45%", "70%"],
          center: ["50%", "52%"],
          avoidLabelOverlap: false,
          label: {
            show: true,
            position: "outside",
            formatter: "{b}",
            fontSize: 10,
            color: tokens.palette.ink,
          },
          labelLine: { length: 10, length2: 10 },
          data: d.demographics,
        },
      ],
    };
  },
  tableDataExtractor: (d: any, gran: any, cfg: any = {}) => {
    const presentation = cfg.presentation || {};
    const tooltipLabel = (presentation.tooltipValueLabels || ["占比"])[0];
    const unit = (presentation.units || [cfg.unit || "%"])[0];
    return {
      headers: presentation.tableHeaders || [
        "类别",
        `${tooltipLabel}${unit ? ` (${unit})` : ""}`,
      ],
      rows: d.demographics.map((segment: any) => [
        segment.name,
        `${segment.value}${unit ? ` ${unit}` : ""}`,
      ]),
    };
  },
};
export default definition;
