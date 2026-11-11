import React, { useEffect, useMemo, useRef, useState } from "react";
import type { ECharts } from "echarts";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";
import { GripVertical } from "lucide-react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardAction,
  CardContent,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  MetricInfoIcon,
} from "./ui";
import { Alert, AlertDescription } from "./components/ui/alert";
import { Skeleton } from "./components/ui/skeleton";
import { MetricCard } from "./metric";
import { DataTable } from "./table";
import { EChartSurface, chartOption, chartData, palette } from "./chart";
import { historicalOption, historicalData } from "./historical-chart";
import { ChartToolbar, IconAction } from "./controls";
import { browserDownload, csvBlob, type Download } from "./host";
import { RecoveryAlert } from "./recovery-alert";
import { SemanticDetails } from "./semantic-details";
import { CustomSurface } from "./custom-surface";
import type { Config, Document, Filter, TableState } from "./types";
class ComponentBoundary extends React.Component<
  { children: React.ReactNode; title: string; resetKey: unknown; onRetry?: () => void },
  { error: string }
> {
  state = { error: "" };
  static getDerivedStateFromError(e: Error) {
    return { error: e.message };
  }
  componentDidUpdate(previous: Readonly<{ resetKey: unknown }>) {
    if (previous.resetKey !== this.props.resetKey && this.state.error)
      this.setState({ error: "" });
  }
  render() {
    return this.state.error ? (
      <RecoveryAlert
        title={`${this.props.title}暂时无法显示`}
        message={this.state.error}
        retryLabel="重新显示"
        onRetry={() => {
          this.setState({ error: "" });
          this.props.onRetry?.();
        }}
      />
    ) : (
      this.props.children
    );
  }
}
function ChartBody({
  config,
  grain,
  table,
  onReady,
  onSelect,
  selectedName,
  context,
}: {
  config: Config;
  grain: string;
  table: boolean;
  onReady: (chart: ECharts | undefined) => void;
  onSelect?: (point: Config) => void;
  selectedName?: string;
  context: { document: Document; id: string };
}) {
  const historical =
    context.document.manifest.components[context.id].kind === "chart";
  const customHtml = config.renderer === "html";
  const grouped = context.document.computed?.grouped?.[context.id];
  const option = useMemo(
    () =>
      customHtml ? null : historical
        ? historicalOption(context.document, context.id, palette)
        : chartOption(config, grain, context),
    [config, grain, context.document.manifest, context.id, grouped],
  );
  const data = useMemo(
    () =>
      table
        ? historical
          ? historicalData(context.document, context.id)
          : chartData(config, grain, context)
        : null,
    [config, grain, table, context.document.manifest, context.id, grouped],
  );
  return (
    <>
      {data && (
      <DataTable
        config={{
          columns: data.headers.map((title, i) => ({ key: String(i), title })),
          rows: data.rows.map((r) =>
            Object.fromEntries(r.map((v, i) => [String(i), v])),
          ),
        }}
        state={{ page: 1, pageSize: Math.max(1, data.rows.length) }}
      />
      )}
      <div className={table ? "hidden" : "flex min-h-0 w-full flex-1"}>
        {customHtml ? <CustomSurface config={config} title={context.document.manifest.components[context.id].title} /> : <EChartSurface
          option={option!}
          label={
            config.title || context.document.manifest.components[context.id].title
          }
          onReady={onReady}
          onSelect={onSelect}
          selectedName={selectedName}
          adaptive={config.renderer !== "echarts"}
        />}
      </div>
    </>
  );
}

// Presentation only: all backend and host actions arrive as callbacks.
export function ComponentView({
  document: doc,
  id,
  grain = "month",
  tableState,
  onTableChange,
  editing = false,
  onGrain,
  onInspect,
  onReadData,
  onExport,
  onSelect,
  selectedName,
  download = browserDownload,
  loading = false,
  error,
  onError,
  onSaveTable,
  onChartType,
  onRetry,
  filters = doc.manifest.filters,
}: {
  document: Document;
  id: string;
  grain?: string;
  tableState?: TableState;
  onTableChange?: (s: TableState) => void;
  editing?: boolean;
  onGrain?: (g: string) => void;
  onInspect?: () => Promise<Config>;
  onReadData?: (state: TableState) => Promise<Config>;
  onExport?: () => Promise<void>;
  onSelect?: (point: Config) => void;
  selectedName?: string;
  download?: Download;
  loading?: boolean;
  error?: string;
  onSaveTable?: () => void;
  onChartType?: (code: string) => Promise<void>;
  onRetry?: () => void;
  filters?: Filter[];
  onError?: (message: string) => void;
}) {
  const c = doc.manifest.components[id],
    family = c.family || c.kind;
  const [table, setTable] = useState(false),
    [details, setDetails] = useState<Config | null>(null),
    [detailError, setDetailError] = useState(""),
    [detailOpen, setDetailOpen] = useState(false),
    [detailLoading, setDetailLoading] = useState(false),
    [tableToolbarTarget, setTableToolbarTarget] = useState<HTMLDivElement | null>(null),
    [actionError, setActionError] = useState(""),
    [expanded, setExpanded] = useState(false);
  const element = useRef<HTMLDivElement>(null),
    chart = useRef<ECharts | undefined>(undefined);
  useEffect(() => {
    const node = element.current;
    if (!node || !["kpi", "chart"].includes(family)) return;
    const fit = () => {
      const width = node.clientWidth, height = node.clientHeight;
      if (!width || !height) return;
      const scale = family === "kpi"
        ? Math.min(width / 420, height / 240)
        : Math.min(width / 560, height / 360);
      node.style.setProperty("--card-scale", String(Math.max(0.875, Math.min(1.5, scale))));
    };
    const observer = new ResizeObserver(fit);
    observer.observe(node);
    fit();
    return () => {
      observer.disconnect();
      node.style.removeProperty("--card-scale");
    };
  }, [family, id]);
  const config =
    doc.computed?.components?.[id] || c.config || c.presentation || {};
  const custom = config.renderer === "echarts" || config.renderer === "html";
  const hasChartTable = !custom || !!config.table;
  const hasChartImage = config.renderer !== "html";
  useEffect(() => {
    if (!hasChartTable) setTable(false);
  }, [hasChartTable]);
  const ready =
    family === "text" ||
    family === "statistical" ||
    !!doc.computed?.grouped?.[id] ||
    !!doc.computed?.components?.[id] ||
    (!c.datasetId && !c.binding);
  const run = (action: () => Promise<void>) => {
    setActionError("");
    void action().catch((e) => {
      const message = e instanceof Error ? e.message : String(e);
      if (onError) onError(message);
      else setActionError(message);
    });
  };
  const inspect = async () => {
    setDetails(null);
    setDetailError("");
    setDetailOpen(true);
    setDetailLoading(true);
    try {
      setDetails((await onInspect?.()) || { component: c });
    } catch (e) {
      setDetailError(String(e));
    } finally {
      setDetailLoading(false);
    }
  };
  const csv = () => {
    const data =
      c.kind === "chart"
        ? historicalData(doc, id)
        : chartData(config, grain, { document: doc, id });
    return download({
      name: id + ".csv",
      mimeType: "text/csv",
      blob: csvBlob(data.headers, data.rows),
    });
  };
  const image = async () => {
    if (!chart.current) throw Error("请切回图表后导出图片。");
    const canvas = chart.current.renderToCanvas({
      pixelRatio: 2,
      backgroundColor: "#fff",
    });
    return new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(Error("图表图片生成失败，请重试。"));
      }, "image/png"),
    );
  };
  const localError = detailError;
  const card = (
        <Card
          className="h-full min-h-0"
          size={family === "kpi" ? "sm" : "default"}
          data-component-id={id}
          data-family={family}
          aria-busy={loading}
        >
          <CardHeader className={`shrink-0${family === "chart" || family === "table" ? " component-header-with-tools" : ""}`}>
            <CardTitle className="flex items-start gap-2">
              {editing && (
                <GripVertical className="resize-handle mt-1 size-4 shrink-0 text-muted-foreground" />
              )}
              <span className="min-w-0 break-words">{c.title}</span>
            </CardTitle>
            {family !== "kpi" && (c.subtitle || config.subtitle) && (
              <CardDescription>
                {c.subtitle || config.subtitle}
              </CardDescription>
            )}
            <CardAction className="component-actions screen-only flex min-w-0 flex-wrap items-center gap-2">
              {family === "table" && <div ref={setTableToolbarTarget} />}
              {family === "chart" ? (
                <ChartToolbar
                  chartType={!custom && editing && onChartType && ["c01", "c02"].includes(config.code) ? config.code : undefined}
                  onChartType={!custom && editing && onChartType && ["c01", "c02"].includes(config.code) ? (code) => run(() => onChartType(code)) : undefined}
                  grain={grain}
                  onGrain={!custom && config.hasGranularity ? onGrain : undefined}
                  showTable={table}
                  onToggle={hasChartTable ? () => setTable(!table) : undefined}
                  onExport={ready && hasChartTable ? () => run(csv) : undefined}
                  onImage={
                    !table && ready && hasChartImage
                      ? () =>
                          run(async () =>
                            download({
                              name: id + ".png",
                              mimeType: "image/png",
                              blob: await image(),
                            }),
                          )
                      : undefined
                  }
                  onCopy={
                    !table &&
                    ready &&
                    hasChartImage &&
                    typeof navigator.clipboard?.write === "function" &&
                    typeof ClipboardItem !== "undefined"
                      ? () =>
                          run(async () => {
                            await navigator.clipboard.write([
                              new ClipboardItem({ "image/png": image() }),
                            ]);
                            toast.success("图表已复制");
                          })
                      : undefined
                  }
                  expanded={expanded}
                  onExpand={() => setExpanded((value) => !value)}
                  onInfo={() => void inspect()}
                />
              ) : (
                <IconAction
                  label={`${c.title} 指标定义与语义`}
                  onClick={() => void inspect()}
                >
                  <MetricInfoIcon />
                </IconAction>
              )}
            </CardAction>
          </CardHeader>
          <CardContent className="relative flex min-h-0 flex-1 flex-col">
          {actionError && (
            <RecoveryAlert title="操作未完成" message={actionError} onRetry={() => setActionError("")} retryLabel="返回组件" />
          )}
          {error ? (
            <RecoveryAlert title={`${c.title}数据未能加载`} message={error} onRetry={onRetry} busy={loading} retryLabel="重新加载数据" />
          ) : !ready ? (
            <div className="flex flex-1 flex-col gap-3">
              <Skeleton className="h-8 w-1/3" />
              <Skeleton className="h-40 w-full" />
            </div>
          ) : family === "kpi" ? (
            <MetricCard config={config} />
          ) : family === "chart" ? (
            <ChartBody
              config={config}
              grain={grain}
              table={table && hasChartTable}
              context={{ document: doc, id }}
              onReady={(instance) => {
                chart.current = instance;
              }}
              onSelect={onSelect}
              selectedName={selectedName}
            />
          ) : family === "table" ? (
            <DataTable
              config={config}
              state={{
                page: 1,
                pageSize: 10,
                ...config.tableState,
                ...doc.computed?.tables?.[id],
                ...tableState,
                columns: tableState?.columns ?? config.tableState?.columns,
                visible: tableState?.visible ?? config.tableState?.visible,
              }}
              onChange={onTableChange}
              onSaveState={editing ? onSaveTable : undefined}
              onExport={onExport ? () => run(onExport) : undefined}
              loading={loading}
              toolbarTarget={tableToolbarTarget}
            />
          ) : family === "text" ? (
            <div className="prose-report overflow-auto">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {c.text || ""}
              </ReactMarkdown>
            </div>
          ) : family === "statistical" ? (
            <Statistical document={doc} id={id} />
          ) : (
            <Alert variant="destructive">
              <AlertDescription>
                此组件类型尚无渲染器：{family}
              </AlertDescription>
            </Alert>
          )}
          </CardContent>
        </Card>
  );
  const detailsDialog = (
        <Dialog
          open={detailOpen || !!localError}
          onOpenChange={(open) => {
            if (!open) {
              setDetailOpen(false);
              setDetails(null);
              setDetailError("");
            }
          }}
        >
          <DialogContent className="flex max-h-[85vh] flex-col gap-0 overflow-hidden rounded-xl bg-white p-0 text-[#17212B] sm:max-w-[720px] [&>[data-slot=dialog-close]]:top-3 [&>[data-slot=dialog-close]]:right-5 [&>[data-slot=dialog-close]]:bg-transparent">
            <DialogHeader className="h-[52px] shrink-0 flex-row items-center gap-2.5 border-b border-border bg-white px-5 pr-16">
                            <DialogTitle className="font-sans text-sm tracking-normal normal-case">{c.title}</DialogTitle>
              <DialogDescription className="sr-only">{family === "table" ? "表格与字段说明" : "图表与指标说明"}</DialogDescription>
            </DialogHeader>
            <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto bg-white px-5 pb-6">
              {localError ? (
                <RecoveryAlert title="指标说明未能加载" message={localError} onRetry={() => void inspect()} busy={detailLoading} retryLabel="重新加载说明" />
              ) : detailLoading ? (
                <p role="status" className="text-sm text-muted-foreground">正在加载指标说明…</p>
              ) : (
                <SemanticDetails value={details} component={c} document={doc} componentId={id} filters={filters} onReadData={onReadData} grain={grain} />
              )}
            </div>
          </DialogContent>
        </Dialog>
  );
  return (
    <ComponentBoundary
      title={c.title}
      resetKey={c.kind === "chart" ? doc.computed?.grouped?.[id] : config}
      onRetry={onRetry}
    >
      <div ref={element} className="flex h-full min-h-0 flex-col">
        {!expanded && card}
        <Dialog open={expanded} onOpenChange={setExpanded}>
          <DialogContent
            showCloseButton={false}
            className="flex h-[calc(100dvh-64px)] max-h-[900px] w-[calc(100vw-48px)] max-w-[1400px] flex-col gap-0 overflow-hidden p-0 sm:max-w-[1400px]"
          >
            <DialogTitle className="sr-only">{c.title} · 放大图表</DialogTitle>
            <DialogDescription className="sr-only">查看放大的当前图表，按 Esc 或点击还原图表返回。</DialogDescription>
            {card}
            {detailsDialog}
          </DialogContent>
        </Dialog>
        {!expanded && detailsDialog}
      </div>
    </ComponentBoundary>
  );
}
function Statistical({
  document: doc,
  id,
}: {
  document: Document;
  id: string;
}) {
  const artifact = doc.statisticalArtifacts?.[id];
  if (!artifact)
    return (
      <p role="status" className="p-5 text-muted-foreground">
        统计图资源尚未加载。
      </p>
    );
  if (artifact.error)
    return (
      <Alert variant="destructive">
        <AlertDescription>{artifact.error}</AlertDescription>
      </Alert>
    );
  const src =
    artifact.dataUri ||
    artifact.dataUrl ||
    (artifact.content
      ? `data:${artifact.mimeType || "image/png"};base64,${artifact.content}`
      : undefined);
  return src ? (
    <img
      className="min-h-0 w-full flex-1 object-contain"
      src={src}
      alt={doc.manifest.components[id].title}
    />
  ) : (
    <Alert variant="destructive">
      <AlertDescription>当前统计图资源没有可显示的图像。</AlertDescription>
    </Alert>
  );
}
