import type React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Alert, AlertDescription } from "./components/ui/alert";
import type { Document } from "./types";

export function AnalyticalReportPage({ document, component }: React.ComponentProps<typeof ReportView>) {
  return (
    <main className="analytical-report-page">
      <ReportView document={document} component={component} />
    </main>
  );
}

export function ReportView({
  document: doc,
  component,
  tableFilters,
}: {
  document: Document;
  component: (id: string) => React.ReactNode;
  tableFilters?: (id: string) => React.ReactNode;
}) {
  const filtered = doc.manifest.viewMode === "filtered-report";
  const figures = new Map<string, number>();
  const numberBlocks = () => (tree: any) => {
    let figure = 0,
      section = 0,
      table = 0;
    for (const [index, block] of tree.children.entries()) {
      if (block.type === "code" && block.lang === "chart") {
        const ref = JSON.parse(block.value);
        const c = doc.manifest.components[ref.componentId];
        const isTable = c?.kind === "table" || (c?.kind === "legacy" && c.family === "table");
        const number = isTable ? ++table : ++figure;
        if (!isTable && !figures.has(ref.componentId)) figures.set(ref.componentId, number);
        block.data = {
          ...block.data,
          hProperties: { ...block.data?.hProperties, "data-figure": number, "data-table": isTable ? "true" : undefined },
        };
      } else if (block.type === "heading" && block.depth === 2) {
        block.data = {
          ...block.data,
          hProperties: {
            ...block.data?.hProperties,
            "data-section": ++section,
          },
        };
      } else if (block.type === "paragraph") {
        const first = block.children[0];
        const label = first?.type === "strong" ? first.children[0]?.value : first?.value;
        const previous = tree.children[index - 1];
        const className =
          previous?.type === "heading" && previous.depth === 1 &&
          block.children.length === 1 && first?.type === "emphasis"
            ? "report-subtitle"
            : label && /^(摘要|abstract)\s*(?:[:：]|$)/i.test(label)
              ? "report-abstract"
              : label && /^(关键词|keywords)\s*(?:[:：]|$)/i.test(label)
                ? "report-keywords"
                : undefined;
        if (className) {
          block.data = { ...block.data, hProperties: { ...block.data?.hProperties, className } };
        }
      }
    }
  };
  return (
    <article className={filtered ? "prose-report prose-report-filtered" : "prose-report"}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, numberBlocks]}
        components={{
          pre: ({ children, node }) => {
            const code = node?.children[0];
            return code?.type === "element" &&
              code.properties["data-figure"] ? (
              <>{children}</>
            ) : (
              <pre>{children}</pre>
            );
          },
          h2: ({ children, node }) => (
            <h2>
              {node?.properties["data-section"]}. {children}
            </h2>
          ),
          a: ({ href, children }) => (
            <a href={href}>
              {href?.startsWith("#fig-") && String(children) === "图"
                ? `图 ${figures.get(href.slice(5)) ?? ""}`
                : children}
            </a>
          ),
          code: ({ className, children, node }) => {
            if (
              className === "language-chart" &&
              node?.properties["data-figure"]
            ) {
              try {
                const ref = JSON.parse(String(children));
                const number = Number(node.properties["data-figure"]);
                if (node.properties["data-table"] === "true") return (
                  <section className="mt-3 mb-6">
                    {ref.caption && <p className="mb-2 text-sm font-medium">表 {number}　{ref.caption}</p>}
                    {tableFilters?.(ref.componentId)}
                    {component(ref.componentId)}
                    {ref.source && <p className="text-xs text-muted-foreground">{ref.source}</p>}
                  </section>
                );
                const definition = doc.manifest.components[ref.componentId];
                const chart = definition?.kind === "chart" || definition?.family === "chart";
                const monochrome = definition?.kind === "chart"
                  ? ["bar", "line"].includes(definition.chartType ?? "")
                  : definition?.family === "chart" &&
                    ["c01", "c02", "t01"].includes(definition.config?.code);
                const caption = ref.caption ?? definition?.title;
                return (
                  <figure
                    id={`fig-${ref.componentId}${figures.get(ref.componentId) === number ? "" : "-" + number}`}
                    className="report-figure"
                    data-report-chart={chart || undefined}
                    data-report-monochrome={monochrome || undefined}
                  >
                    <div className={chart ? "report-plot" : "h-[420px]"}>
                      {component(ref.componentId)}
                    </div>
                    <figcaption>
                      图 {number}
                      {caption ? `　${caption}` : ""}
                    </figcaption>
                    {ref.source && (
                      <p className="report-figure-source">
                        {ref.source}
                      </p>
                    )}
                  </figure>
                );
              } catch (e) {
                return (
                  <Alert variant="destructive">
                    <AlertDescription>
                      图表引用无效：{String(e)}
                    </AlertDescription>
                  </Alert>
                );
              }
            }
            return <code className={className}>{children}</code>;
          },
        }}
      >
        {doc.manifest.report?.markdown || ""}
      </ReactMarkdown>
    </article>
  );
}
