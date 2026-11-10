import type React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Alert, AlertDescription } from "./components/ui/alert";
import type { Document } from "./types";
export function ReportView({
  document: doc,
  component,
}: {
  document: Document;
  component: (id: string) => React.ReactNode;
}) {
  const figures = new Map<string, number>();
  const numberBlocks = () => (tree: any) => {
    let figure = 0,
      section = 0;
    for (const block of tree.children) {
      if (block.type === "code" && block.lang === "chart") {
        const ref = JSON.parse(block.value);
        figure++;
        if (!figures.has(ref.componentId)) figures.set(ref.componentId, figure);
        block.data = {
          ...block.data,
          hProperties: { ...block.data?.hProperties, "data-figure": figure },
        };
      } else if (block.type === "heading" && block.depth === 2) {
        block.data = {
          ...block.data,
          hProperties: {
            ...block.data?.hProperties,
            "data-section": ++section,
          },
        };
      }
    }
  };
  return (
    <article className="prose-report">
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
                return (
                  <figure
                    id={`fig-${ref.componentId}${figures.get(ref.componentId) === number ? "" : "-" + number}`}
                    className="my-6"
                  >
                    <div className="h-[420px]">
                      {component(ref.componentId)}
                    </div>
                    <figcaption className="mt-2 text-sm">
                      图 {number}
                      {ref.caption ? `　${ref.caption}` : ""}
                    </figcaption>
                    {ref.source && (
                      <p className="text-xs text-muted-foreground">
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
