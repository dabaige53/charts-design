import React, { useEffect, useRef, useState } from "react";
import {
  RefreshCw,
  Pencil,
  Save,
  X,
  Maximize2,
  Minimize2,
  History,
  FileDown,
  SlidersHorizontal,
  Search,
  RotateCcw,
  MessageSquareText,
  MousePointer2,
} from "lucide-react";
import { toast } from "sonner";
import { useFullscreenElement } from "./fullscreen";
import {
  Button,
} from "./ui";
import { Input } from "./components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./components/ui/dialog";
import { Field, FieldLabel } from "./components/ui/field";
import { Badge } from "./components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "./components/ui/popover";
import { InputGroup, InputGroupAddon, InputGroupInput } from "./components/ui/input-group";
import { Empty, EmptyHeader, EmptyTitle } from "./components/ui/empty";
import { ComponentView } from "./component-view";
import { DashboardGrid } from "./grid";
import { ReportView } from "./report";
import {
  ActiveFilters,
  ChoiceSelect,
  DateRangeFilter,
  IconAction,
  MultiSelect,
  RangeFilter,
  type ChoiceLoader,
} from "./controls";
import { useDashboardRuntime, layoutOperations } from "./runtime";
import { browserDownload, deliverExport, type Download } from "./host";
import { RecoveryAlert } from "./recovery-alert";
import { PositionComments } from "./position-comments";
import { VersionCenter } from "./version-center";
import { useVisibleVersionCheck } from "./resource-refresh";
import type { Config, Document, Filter, Position, ToolCall } from "./types";
function VisibleComponent({
  id,
  onVisible,
  children,
}: {
  id: string;
  onVisible: (id: string) => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          onVisible(id);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(ref.current!);
    return () => observer.disconnect();
  }, [id, onVisible]);
  return (
    <div ref={ref} className="h-full min-h-0">
      {children}
    </div>
  );
}

export function DashboardApp({
  initial,
  call,
  onFullscreen,
  pageFullscreen = false,
  download = browserDownload,
  readOnly = false,
  staticMode = false,
  buildId,
  primaryFilterIds,
  projectRoot,
}: {
  initial: Document;
  call: ToolCall;
  onFullscreen?: () => void;
  pageFullscreen?: boolean;
  download?: Download;
  readOnly?: boolean;
  staticMode?: boolean;
  buildId?: string;
  primaryFilterIds?: string[];
  projectRoot?: string | null;
}) {
  const runtime = useDashboardRuntime(initial, call),
    doc = runtime.document;
  const fullscreenElement = useFullscreenElement();
  const isPageFullscreen = pageFullscreen || fullscreenElement === document.documentElement;
  const editUnavailable = "此链接为查看预览，请使用编辑预览链接操作";
  const [editing, setEditing] = useState(false),
    [title, setTitle] = useState(initial.manifest.title),
    [boards, setBoards] = useState<Config[]>([]),
    [versionsOpen, setVersionsOpen] = useState(false),
    [versionSwitchOpen, setVersionSwitchOpen] = useState(false),
    [switchingId, setSwitchingId] = useState<string | null>(null),
    [notesOpen, setNotesOpen] = useState(false),
    [annotationBusy, setAnnotationBusy] = useState(false),
    [layoutKey, setLayoutKey] = useState(0);
  const annotationRoot = useRef<HTMLDivElement>(null);
  const navigationSequence = useRef(0);
  const draft = useRef<Record<string, Position[]>>({});
  useEffect(() => {
    setTitle(doc.manifest.title);
  }, [doc.id, doc.manifest.title]);
  useEffect(() => {
    let live = true;
    call("dashboard_list")
      .then((r) => {
        if (live) setBoards(r.dashboards);
      })
      .catch((e) => runtime.setError(String(e)));
    return () => {
      live = false;
    };
  }, [call, doc.id]);
  useVisibleVersionCheck({
    call, dashboardId: doc.id, revision: doc.revision, buildId, staticMode,
    blocked: editing || annotationBusy || notesOpen || runtime.saving,
    reload: runtime.reload, setError: runtime.setError,
  });
  const guard = (work: () => Promise<void>) => {
    void work().catch((e) => runtime.setError(String(e)));
  };
  const deliver = (file: Config) =>
    deliverExport(file, download, (offset, limit) =>
      call("dashboard_export_read", {
        dashboardId: doc.id,
        exportId: file.id,
        format: file.format,
        offset,
        limit,
      }),
    );
  const exportTable = async (id: string) => {
    const state = runtime.view.tables[id] || doc.computed?.tables?.[id] || {};
    const result = await call("dataset_export", {
      dashboardId: doc.id,
      componentId: id,
      filters: runtime.view.filters,
      search: state.keyword || "",
      ...(state.sortCol
        ? {
            sort: [{ field: state.sortCol, direction: state.sortDir || "asc" }],
          }
        : {}),
      ...(state.visible
        ? {
            columns: (state.columns ?? state.visible).filter((key: string) =>
              state.visible!.includes(key),
            ),
          }
        : {}),
    });
    await deliver(result.export);
  };
  const link = (id: string, point: Config) => {
    const c = doc.manifest.components[id],
      binding = c.binding;
    if (!binding?.categoryField || !binding.datasetId) return;
    const value =
      c.config?.code === "r02" ? (point.value?.[3] ?? point.name) : point.name;
    if (value == null) return;
    const old = runtime.view.filters.find((f) => f.id === "runtime-linkage");
    const consumers = Object.entries(doc.manifest.components)
      .filter(
        ([key, target]) =>
          key !== id &&
          (target.datasetId === binding.datasetId ||
            target.binding?.datasetId === binding.datasetId ||
            (c.linkGroup &&
              target.linkGroup === c.linkGroup &&
              doc.manifest.datasets[
                target.datasetId || target.binding?.datasetId
              ]?.fields?.[binding.categoryField])),
      )
      .map(([key]) => key);
    if (!consumers.length) return;
    runtime.link({
      id: "runtime-linkage",
      label: c.title,
      field: binding.categoryField,
      op: "in",
      values: runtime.view.linkageSource === id && old?.values[0] === value ? [] : [value],
      componentIds: consumers,
    }, id);
  };
  const saveTable = async (id: string) => {
    const c = doc.manifest.components[id],
      state = runtime.view.tables[id] ?? {},
      config = doc.computed?.components[id] ?? c.config ?? c.presentation ?? {};
    const keys = (config.columns || []).map((column: Config) => column.key),
      saved = {
        columns: state.columns ?? keys,
        visible: state.visible ?? keys,
      };
    const value =
      c.kind === "legacy"
        ? {
            ...c,
            config: {
              ...c.config,
              tableState: { ...c.config?.tableState, ...saved },
            },
          }
        : {
            ...c,
            presentation: {
              ...c.presentation,
              tableState: { ...c.presentation?.tableState, ...saved },
            },
          };
    if (await runtime.save([{ op: "put_component", id, value }]))
      toast.success("列配置已保存");
  };
  const component = (id: string) => (
    <VisibleComponent key={id} id={id} onVisible={runtime.activate}>
      <ComponentView
        document={doc}
        id={id}
        editing={editing}
        grain={runtime.view.grains[id] || "month"}
        onGrain={(g) => runtime.setGrain(id, g)}
        tableState={runtime.view.tables[id]}
        onTableChange={(s) => runtime.setTable(id, s)}
        onInspect={() =>
          call("semantic_inspect", { dashboardId: doc.id, componentId: id })
        }
        onReadData={(doc.manifest.components[id].datasetId || doc.manifest.components[id].binding?.datasetId || doc.staticComponentDatasets?.[id])
          ? (state) => call("component_data", {
              dashboardId: doc.id,
              componentId: id,
              expectedRevision: doc.revision,
              filters: runtime.view.filters,
              offset: (state.page - 1) * state.pageSize,
              limit: state.pageSize,
              search: state.keyword || "",
              ...(state.sortCol ? { sort: [{ field: state.sortCol, direction: state.sortDir || "asc" }] } : {}),
            })
          : undefined}
        onExport={() => exportTable(id)}
        onSaveTable={() => guard(() => saveTable(id))}
        onChartType={async (code) => {
          if (await runtime.save([{ op: "set_original_chart", id, code }]))
            toast.success("图表类型已保存");
        }}
        onSelect={(point) => link(id, point)}
        selectedName={runtime.view.linkageSource === id
          ? runtime.view.filters.find((filter) => filter.id === "runtime-linkage")?.values[0]
          : undefined}
        download={download}
        loading={runtime.loading.includes(id)}
        error={runtime.errors[id]}
        onError={runtime.setError}
        onRetry={() => void runtime.retry(id)}
        filters={runtime.view.filters}
      />
    </VisibleComponent>
  );
  return (
    <div ref={annotationRoot} className="min-h-screen bg-canvas">
      <header className="dashboard-header flex flex-wrap items-center justify-between gap-3 border-b border-border bg-card px-6 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="min-w-0">
            {editing ? (
              <Input
                aria-label="看板标题"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            ) : (
              <h1 className="text-xl font-semibold text-brand">
                {doc.manifest.title}
              </h1>
            )}
            {doc.manifest.meta?.subtitle && (
              <p className="mt-1 text-xs text-muted-foreground">
                {doc.manifest.meta.subtitle}
              </p>
            )}
          </div>
        </div>
        <div data-annotation-ui role="group" aria-label="看板操作" className="screen-only flex flex-wrap items-center gap-2 max-sm:w-full max-sm:[&>[data-slot=field]]:basis-full">
          {boards.length > 1 && (
            <ChoiceSelect
              label="切换看板"
              labelHidden
              value={switchingId || doc.id}
              disabled={editing || runtime.saving || annotationBusy || notesOpen || !!switchingId}
              options={boards.map((b) => ({
                value: b.id,
                label: b.title || b.id,
              }))}
              onChange={(id) =>
                guard(async () => {
                  const sequence = ++navigationSequence.current;
                  setSwitchingId(id);
                  try {
                    const result = await call("dashboard_get", {
                      dashboardId: id,
                      dataMode: "local",
                    });
                    if (sequence !== navigationSequence.current) return;
                    setEditing(false);
                    draft.current = {};
                    runtime.accept(result.document);
                  } finally {
                    if (sequence === navigationSequence.current) setSwitchingId(null);
                  }
                })
              }
            />
          )}
          {switchingId && <span role="status" className="sr-only">正在切换…</span>}
          <IconAction
            label="刷新报表"
            disabled={editing || runtime.saving || annotationBusy || notesOpen}
            onClick={() => void runtime.reload()}
          >
            <RefreshCw />
          </IconAction>
          <IconAction label={isPageFullscreen ? "退出页面全屏" : "页面全屏"} onClick={onFullscreen} pressed={isPageFullscreen}>
            {isPageFullscreen ? <Minimize2 /> : <Maximize2 />}
          </IconAction>
          {(
            <IconAction
              label={notesOpen ? "退出位置批注" : readOnly ? "查看批注" : "添加位置批注"}
              pressed={notesOpen}
              variant={notesOpen ? "default" : "ghost"}
              disabled={staticMode || editing || runtime.saving}
              unavailable={staticMode ? editUnavailable : "请先完成当前编辑"}
              onClick={() => setNotesOpen((value) => !value)}
            >
              {notesOpen && !readOnly ? <MousePointer2 /> : <MessageSquareText />}
            </IconAction>
          )}
          {(
            <IconAction
              label="版本与分享"
              disabled={readOnly || runtime.saving || annotationBusy || notesOpen}
              unavailable={readOnly ? editUnavailable : "请先完成当前编辑"}
              onClick={() => editing ? setVersionSwitchOpen(true) : setVersionsOpen(true)}
            >
              <History />
            </IconAction>
          )}
          {(
            <IconAction
              label="导出 HTML"
              disabled={staticMode}
              unavailable="请在编辑预览页导出 HTML"
              onClick={() =>
                guard(async () => {
                  const result = await call("dashboard_export", {
                    dashboardId: doc.id,
                    format: "html",
                    filters: runtime.view.filters,
                    tableStates: runtime.view.tables,
                    granularities: runtime.view.grains,
                  });
                  await deliver(result.export);
                })
              }
            >
              <FileDown />
            </IconAction>
          )}
          {(editing ? (
              <>
                <IconAction
                  label="取消布局编辑"
                  disabled={runtime.saving}
                  unavailable="正在保存，请稍候"
                  onClick={() => {
                    setEditing(false);
                    draft.current = {};
                    setTitle(doc.manifest.title);
                    setLayoutKey((v) => v + 1);
                  }}
                >
                  <X />
                </IconAction>
                <IconAction
                  label={runtime.saving ? "正在保存布局…" : "保存布局"}
                  variant="default"
                  disabled={runtime.saving}
                  unavailable="正在保存，请稍候"
                  onClick={() =>
                    guard(async () => {
                      const operations = layoutOperations(title, draft.current);
                      if (await runtime.save(operations)) {
                        setEditing(false);
                        draft.current = {};
                        toast.success("布局已保存");
                      }
                    })
                  }
                >
                  <Save />
                </IconAction>
              </>
            ) : (
              <IconAction
                label="编辑布局"
                disabled={readOnly || runtime.saving || annotationBusy || notesOpen}
                unavailable={readOnly ? editUnavailable : "请先完成当前操作"}
                onClick={() =>
                  guard(async () => {
                    const result = await call("dashboard_get", { dashboardId: doc.id });
                    if (result.document.revision !== doc.revision) {
                      runtime.setError("草稿与当前保存版本不同，请先完成保存，再重新加载后编辑。");
                      return;
                    }
                    setEditing(true);
                  })
                }
              >
                <Pencil />
              </IconAction>
            ))}
        </div>
      </header>
      <main className="dashboard-main mx-auto max-w-[1800px] p-4">
        {runtime.error && (
          <RecoveryAlert
            className="mb-4"
            title="部分数据或操作未能完成"
            message={runtime.error}
            onRetry={editing ? () => runtime.setError("") : () => void runtime.reload()}
            retryLabel={editing ? "继续编辑" : "重新加载数据"}
            busy={runtime.saving}
          />
        )}
        {editing && (
          <p className="sr-only" role="status">
            拖动标题旁的手柄，或缩放组件右下角。保存将创建版本检查点。
          </p>
        )}
        <FilterBar
          document={doc}
          filters={runtime.view.filters}
          call={call}
          onChange={runtime.setFilter}
          onClear={runtime.clear}
          primaryFilterIds={primaryFilterIds}
        />
        {doc.manifest.viewMode === "report" ? (
          <ReportView document={doc} component={component} />
        ) : (
          <DashboardGrid
            key={`${doc.id}:${layoutKey}`}
            document={doc}
            editing={editing}
            onLayoutChange={(positions, bp) => {
              draft.current[bp] = positions;
            }}
          >
            {component}
          </DashboardGrid>
        )}
        {!Object.keys(doc.manifest.components).length && (
          <Empty>
            <EmptyHeader>
              <EmptyTitle>此看板还没有组件</EmptyTitle>
            </EmptyHeader>
          </Empty>
        )}
      </main>
      {!staticMode && !editing && (
        <PositionComments
          key={JSON.stringify([projectRoot, doc.id])}
          document={doc}
          root={annotationRoot}
          active={notesOpen}
          onActiveChange={setNotesOpen}
          onActivityChange={setAnnotationBusy}
          call={call}
          readOnly={readOnly}
          filters={runtime.view.filters}
          projectRoot={projectRoot}
          onNotesChange={runtime.setAnnotations}
        />
      )}
      {!readOnly && <VersionCenter
        open={versionsOpen}
        onOpenChange={setVersionsOpen}
        document={doc}
        call={call}
        onSaved={async () => {
          const result = await call("dashboard_get", { dashboardId: doc.id });
          runtime.accept(result.document);
        }}
        onRestore={async (revision) => {
          await runtime.restore(revision);
          setLayoutKey((value) => value + 1);
        }}
      />}
      <Dialog open={versionSwitchOpen} onOpenChange={setVersionSwitchOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>打开历史版本前处理当前编辑</DialogTitle>
            <DialogDescription>历史预览不会覆盖草稿。请选择如何处理当前尚未保存的布局和标题。</DialogDescription></DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setVersionSwitchOpen(false)}>取消</Button>
            <Button variant="outline" onClick={() => {
              setEditing(false); draft.current = {}; setTitle(doc.manifest.title); setLayoutKey(value => value + 1);
              setVersionSwitchOpen(false); setVersionsOpen(true);
            }}>放弃修改并切换</Button>
            <Button disabled={runtime.saving} onClick={() => guard(async () => {
              if (await runtime.save(layoutOperations(title, draft.current))) {
                setEditing(false); draft.current = {}; setVersionSwitchOpen(false); setVersionsOpen(true);
              }
            })}>保存后切换</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
function SelectionFilter({
  filter,
  options,
  call,
  onChange,
  dashboardId,
}: {
  filter: Filter;
  options: any[];
  call: ToolCall;
  onChange: (values: any[]) => void;
  dashboardId: string;
}) {
  const load: ChoiceLoader = React.useCallback(
    async (search, offset) => {
      const result = await call("dashboard_filter_options", {
        dashboardId,
        filterId: filter.id,
        search,
        offset,
        limit: 100,
      });
      return {
        options: result.values.map((value: any) => ({
          value: JSON.stringify(value),
          label: String(value),
        })),
        hasMore: result.hasMore,
        total: result.totalValues,
      };
    },
    [call, dashboardId, filter.id],
  );
  return (
    <MultiSelect
      label={filter.label}
      labelHidden
      single={filter.selectionMode === "single"}
      options={[...options, ...filter.values].map((v) => ({
        value: JSON.stringify(v),
        label: String(v),
      }))}
      value={filter.values.map((v) => JSON.stringify(v))}
      onChange={(values) => onChange(values.map((v) => JSON.parse(v)))}
      loadOptions={load}
    />
  );
}
function FilterControl({
  filter: f,
  document: doc,
  call,
  onChange,
}: {
  filter: Filter;
  document: Document;
  call: ToolCall;
  onChange: (id: string, values: any[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const field = Object.values(doc.manifest.datasets)
    .map((ds) => ds.fields?.[f.field]).find(Boolean);
  const range: [string, string] = [String(f.values[0] ?? ""), String(f.values[1] ?? "")];
  if (f.op === "in")
    return (
      <SelectionFilter
        filter={f}
        options={doc.computed?.filterOptions?.[f.id] || []}
        call={call}
        dashboardId={doc.id}
        onChange={(values) => onChange(f.id, values)}
      />
    );
  if (f.op === "contains")
    return (
      <Field className="w-52 max-w-full">
        <FieldLabel htmlFor={"filter-" + f.id} className="sr-only">{f.label}</FieldLabel>
        <InputGroup>
          <InputGroupAddon><Search /></InputGroupAddon>
          <InputGroupInput
            id={"filter-" + f.id}
            value={f.values[0] ?? ""}
            onChange={(e) => onChange(f.id, e.target.value ? [e.target.value] : [])}
            placeholder={f.label}
          />
        </InputGroup>
      </Field>
    );
  if (field?.type === "date")
    return (
      <DateRangeFilter
        label={f.label}
        labelHidden
        value={range}
        onApply={(from, to) => onChange(f.id, from && to ? [from, to] : [])}
      />
    );
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" aria-label={`${f.label}范围`}>
          <span className="text-muted-foreground">{f.label}</span>
          {f.values.length ? f.values.join(" — ") : "不限"}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-96 max-w-[calc(100vw-2rem)]">
        <RangeFilter
          label={f.label}
          value={range}
          type={field?.type === "number" ? "number" : "text"}
          onApply={(from, to) => {
            onChange(f.id, from && to
              ? field?.type === "number" ? [Number(from), Number(to)] : [from, to]
              : []);
            setOpen(false);
          }}
        />
      </PopoverContent>
    </Popover>
  );
}
function FilterBar({
  document: doc,
  filters,
  call,
  onChange,
  onClear,
  primaryFilterIds,
}: {
  document: Document;
  filters: Filter[];
  call: ToolCall;
  onChange: (id: string, values: any[]) => void;
  onClear: () => void;
  primaryFilterIds?: string[];
}) {
  const [expanded, setExpanded] = useState(false);
  const advancedId = React.useId();
  if (!filters.length) return null;
  const declared = filters.filter((f) => f.id !== "runtime-linkage");
  const primary = primaryFilterIds
    ? [...new Set(primaryFilterIds)].flatMap((id) => declared.filter((filter) => filter.id === id))
    : declared.filter((f) => f.op !== "contains").slice(0, 3);
  const advanced = declared.filter((f) => !primary.includes(f));
  const activeAdvanced = advanced.filter((f) => f.values.length).length;
  const active = filters.flatMap((f) =>
    f.op === "in"
      ? f.values.map((value, index) => ({
          id: JSON.stringify([f.id, index]),
          label: `${f.label}：${String(value)}`,
        }))
      : f.values.length
        ? [{ id: JSON.stringify([f.id, -1]), label: `${f.label}：${f.values.join(" — ")}` }]
        : [],
  );
  return (
    <section
      aria-label="看板筛选"
      className="screen-only mb-3 flex flex-col gap-2 border border-border bg-card p-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {primary.map((f) => (
            <FilterControl key={f.id} filter={f} document={doc} call={call} onChange={onChange} />
          ))}
        </div>
        {!!advanced.length && (
          <Button
            variant={expanded ? "secondary" : "outline"}
            aria-expanded={expanded}
            aria-controls={advancedId}
            onClick={() => setExpanded(!expanded)}
          >
            <SlidersHorizontal data-icon="inline-start" />
            更多筛选
            {activeAdvanced > 0 && <Badge variant="secondary">{activeAdvanced}</Badge>}
          </Button>
        )}
        {!!active.length && (
          <IconAction label="重置全部筛选" onClick={onClear} size="icon-sm">
            <RotateCcw />
          </IconAction>
        )}
      </div>
      {!!advanced.length && (
        <div className="filter-advanced-row" data-expanded={expanded} inert={!expanded}>
          <div className="min-h-0 overflow-hidden">
            <div id={advancedId} aria-label="更多筛选条件" className="flex flex-wrap items-center gap-2">
              {advanced.map((f) => (
                <FilterControl key={f.id} filter={f} document={doc} call={call} onChange={onChange} />
              ))}
            </div>
          </div>
        </div>
      )}
      <div className="filter-active-row" data-active={!!active.length} inert={!active.length}>
      <div className="min-h-0 overflow-hidden">
      <ActiveFilters
        items={active}
        showClear={false}
        onRemove={(token) => {
          const [id, index] = JSON.parse(token);
          const filter = filters.find((f) => f.id === id)!;
          onChange(
            id,
            index < 0 ? [] : filter.values.filter((_, i) => i !== index),
          );
        }}
        onClear={onClear}
      />
      </div>
      </div>
    </section>
  );
}
