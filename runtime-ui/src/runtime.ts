import { useCallback, useEffect, useRef, useState } from "react";
import { createRequestQueue } from "../../dashboard_runtime/web/request-queue.mjs";
import type {
  Config,
  Document,
  Filter,
  Position,
  TableState,
  ToolCall,
} from "./types";

type View = {
  filters: Filter[];
  tables: Record<string, TableState>;
  grains: Record<string, string>;
  linkageSource?: string;
};
export function mergeView(document: Document, patch: Config): Document {
  return {
    ...document,
    statisticalArtifacts: {
      ...document.statisticalArtifacts,
      ...patch.statisticalArtifacts,
    },
    computed: {
      ...document.computed,
      ...patch.computed,
      ...Object.fromEntries(
        ["components", "tables", "grouped", "filterOptions", "filterPages"].map(
          (key) => [
            key,
            {
              ...document.computed?.[
                key as keyof NonNullable<Document["computed"]>
              ],
              ...patch.computed?.[key],
            },
          ],
        ),
      ),
    },
  };
}

export function useDashboardRuntime(initial: Document, call: ToolCall) {
  const [document, setDocument] = useState(initial),
    [view, setView] = useState<View>({
      filters: initial.manifest.filters,
      tables: {},
      grains: {},
    });
  const [loading, setLoading] = useState<string[]>([]),
    [error, setError] = useState(""),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [saving, setSaving] = useState(false);
  const current = useRef(initial),
    reader = useRef(view),
    generation = useRef(0),
    active = useRef(new Set<string>()),
    loaded = useRef(new Set<string>());
  const pending = useRef(new Map<string, number>()),
    versions = useRef(new Map<string, number>()),
    live = useRef(true);
  const queue = useRef(createRequestQueue(4));
  const request = useCallback(
    (ids: string[]) => {
      const token = generation.current,
        doc = current.current,
        values = reader.current;
      const keys = [...new Set(ids)].filter((id) => {
        const component = doc.manifest.components[id];
        return component && component.kind !== "text" &&
          (component.kind !== "legacy" || component.binding) &&
          !pending.current.has(id);
      });
      if (!keys.length) return Promise.resolve();
      const requested = new Map(keys.map((id) => [id, versions.current.get(id) ?? token]));
      const isCurrent = (id: string) =>
        live.current &&
        versions.current.get(id) === requested.get(id) &&
        current.current.id === doc.id &&
        current.current.revision === doc.revision;
      keys.forEach((id) => {
        versions.current.set(id, requested.get(id)!);
        pending.current.set(id, requested.get(id)!);
      });
      setLoading((list) => [...new Set([...list, ...keys])]);
      setErrors((previous) =>
        Object.fromEntries(
          Object.entries(previous).filter(([id]) => !keys.includes(id)),
        ),
      );
      const run = async () => {
        let next = 0;
        const worker = async () => {
          while (next < keys.length) {
            const id = keys[next++];
            try {
              if (!isCurrent(id)) continue;
              const patch = await queue.current(() =>
                isCurrent(id) ? call("dashboard_view", {
                  dashboardId: doc.id,
                  expectedRevision: doc.revision,
                  ...(doc.dataVersion ? { dataVersion: doc.dataVersion } : {}),
                  filterSequence: token,
                  filters: values.filters,
                  tableStates: {
                    ...values.tables,
                    ...(doc.manifest.components[id]?.kind === "table" && !values.tables[id]
                      ? { [id]: { page: 1, pageSize: doc.manifest.components[id].config?.tableState?.pageSize ?? doc.manifest.components[id].presentation?.tableState?.pageSize ?? 10 } }
                      : {}),
                  },
                  granularities: values.grains,
                  responseMode: "patch",
                  componentIds: [id],
                  compactRecords: true,
                }) : Promise.resolve(null),
              );
              if (!patch || !isCurrent(id)) continue;
              if (patch.id !== doc.id || patch.revision !== doc.revision)
                throw Error("查看结果与当前看板版本不一致，请刷新。");
              if (isCurrent(id)) {
                loaded.current.add(id);
                if (patch.computed?.tables?.[id]) {
                  const nextView = {
                    ...reader.current,
                    tables: {
                      ...reader.current.tables,
                      [id]: {
                        ...reader.current.tables[id],
                        ...patch.computed.tables[id],
                      },
                    },
                  };
                  reader.current = nextView;
                  setView(nextView);
                }
                setDocument((previous) => mergeView(previous, patch));
              }
            } catch (e) {
              if (isCurrent(id)) {
                const message = e instanceof Error ? e.message : String(e);
                setErrors((previous) => ({ ...previous, [id]: message }));
              }
            } finally {
              if (pending.current.get(id) === requested.get(id)) {
                pending.current.delete(id);
                if (live.current)
                  setLoading((list) => list.filter((key) => key !== id));
              }
            }
          }
        };
        await Promise.all(
          Array.from({ length: Math.min(4, keys.length) }, worker),
        );
      };
      return run();
    },
    [call],
  );
  const invalidate = useCallback(
    (next: View, ids?: string[]) => {
      generation.current++;
      const affected = new Set(ids ?? Object.keys(current.current.manifest.components));
      affected.forEach((id) => {
        versions.current.set(id, generation.current);
        pending.current.delete(id);
        loaded.current.delete(id);
      });
      setLoading((list) => list.filter((id) => !affected.has(id)));
      setError("");
      reader.current = next;
      setView(next);
      void request([...affected].filter((id) => active.current.has(id)));
    },
    [request],
  );
  const accept = useCallback(
    (doc: Document, preserveView = false) => {
      generation.current++;
      pending.current.clear();
      versions.current.clear();
      loaded.current.clear();
      setLoading([]);
      setError("");
      setErrors({});
      const sameDashboard = current.current.id === doc.id;
      current.current = doc;
      setDocument((previous) =>
        preserveView && previous.id === doc.id && previous.dataVersion === doc.dataVersion
          ? { ...doc, computed: previous.computed, statisticalArtifacts: previous.statisticalArtifacts }
          : doc,
      );
      const previous = reader.current;
      const next: View = preserveView
        ? {
            filters: doc.manifest.filters.map((f) => ({
              ...f,
              values:
                previous.filters.find(
                  (old) =>
                    old.id === f.id && old.field === f.field && old.op === f.op,
                )?.values ?? f.values,
            })),
            tables: Object.fromEntries(
              Object.entries(previous.tables).filter(
                ([id]) => !!doc.manifest.components[id],
              ),
            ),
            grains: Object.fromEntries(
              Object.entries(previous.grains).filter(
                ([id]) => !!doc.manifest.components[id],
              ),
            ),
          }
        : { filters: doc.manifest.filters, tables: {}, grains: {} };
      reader.current = next;
      setView(next);
      active.current = new Set(
        sameDashboard ? [...active.current].filter((id) => !!doc.manifest.components[id]) : [],
      );
      void request([...active.current]);
    },
    [request],
  );
  useEffect(() => {
    live.current = true;
    accept(initial);
    return () => {
      live.current = false;
      generation.current++;
      versions.current.clear();
      pending.current.clear();
    };
  }, [initial, accept]);
  const activate = useCallback(
    (id: string) => {
      active.current.add(id);
      if (!loaded.current.has(id)) void request([id]);
    },
    [request],
  );
  const setFilter = (id: string, values: any[]) => {
    const filter = reader.current.filters.find((item) => item.id === id);
    if (!filter || (filter.values.length === values.length && filter.values.every((value, index) => value === values[index]))) return;
    const targets = new Set(filter.componentIds);
    invalidate({
      ...reader.current,
      filters: reader.current.filters.map((f) =>
        f.id === id ? { ...f, values } : f,
      ),
      tables: Object.fromEntries(
        Object.entries(reader.current.tables).map(([key, state]) => [
          key,
          targets.has(key) ? { ...state, page: 1 } : state,
        ]),
      ),
    }, filter.componentIds);
  };
  const setTable = (id: string, state: TableState) => {
    const before = reader.current.tables[id];
    const next = {
      ...reader.current,
      tables: { ...reader.current.tables, [id]: state },
    };
    if (
      before &&
      before.keyword === state.keyword &&
      before.page === state.page &&
      before.pageSize === state.pageSize &&
      before.sortCol === state.sortCol &&
      before.sortDir === state.sortDir
    ) {
      reader.current = next;
      setView(next);
      return;
    }
    invalidate(next, [id]);
  };
  const setGrain = (id: string, grain: string) =>
    invalidate({
      ...reader.current,
      grains: { ...reader.current.grains, [id]: grain },
    }, [id]);
  const clear = () =>
    invalidate({
      ...reader.current,
      filters: reader.current.filters
        .filter((f) => f.id !== "runtime-linkage")
        .map((f) => ({ ...f, values: [] })),
      tables: {},
    });
  const link = (filter: Filter, sourceId: string) => {
    const previous = reader.current.filters.find((item) => item.id === "runtime-linkage");
    const targets = [...new Set([...(previous?.componentIds ?? []), ...filter.componentIds])];
    invalidate({
      ...reader.current,
      linkageSource: filter.values.length ? sourceId : undefined,
      filters: [
        ...reader.current.filters.filter((f) => f.id !== "runtime-linkage"),
        filter,
      ],
      tables: {},
    }, targets);
  };
  const reload = async () => {
    try {
      setError("");
      const result = await call("dashboard_preview", {
        dashboardId: current.current.id,
      });
      accept(result.document, true);
    } catch (e) {
      setError(String(e));
    }
  };
  const save = async (operations: Config[]) => {
    setSaving(true);
    setError("");
    try {
      const doc = current.current;
      if (doc.progressive) {
        const batch = await call("dashboard_edit_begin", {
          dashboardId: doc.id,
          expectedRevision: doc.revision,
        });
        const patched = await call("dashboard_patch", {
          dashboardId: doc.id,
          expectedRevision: doc.revision,
          operations,
        });
        current.current = patched.document;
        const finished = await call("dashboard_edit_finish", {
          dashboardId: doc.id,
          expectedRevision: patched.document.revision,
          batchId: batch.batch_id,
        });
        if (!finished.ok)
          throw Error(
            "保存的草稿未通过检查，尚未生成检查点。请查看指标定义与数据绑定。",
          );
      } else {
        current.current = (
          await call("dashboard_patch", {
            dashboardId: doc.id,
            expectedRevision: doc.revision,
            operations,
          })
        ).document;
      }
      const result = await call("dashboard_get", {
        dashboardId: doc.id,
        dataMode: "local",
      });
      accept(result.document, true);
      return true;
    } catch (e) {
      setError(String(e));
      return false;
    } finally {
      setSaving(false);
    }
  };
  const restore = async (revision: number) => {
    setSaving(true);
    setError("");
    try {
      const result = await call("dashboard_restore", {
        dashboardId: current.current.id,
        expectedRevision: current.current.revision,
        revision,
      });
      accept(result.document);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };
  const setAnnotations = useCallback((annotations: Config[]) => {
    current.current = {
      ...current.current,
      manifest: { ...current.current.manifest, annotations },
    };
    setDocument((previous) => ({
      ...previous,
      manifest: { ...previous.manifest, annotations },
    }));
  }, []);
  return {
    document,
    view,
    loading,
    error,
    errors,
    saving,
    activate,
    setFilter,
    setTable,
    setGrain,
    clear,
    link,
    reload,
    save,
    restore,
    accept,
    setError,
    setAnnotations,
    loaded,
    retry: (id: string) => request([id]),
  };
}

export function layoutOperations(
  title: string,
  layouts: Record<string, Position[]>,
) {
  return [
    { op: "set_title", value: title },
    ...Object.entries(layouts).map(([breakpoint, value]) => ({
      op: "set_layout",
      breakpoint,
      value,
    })),
  ];
}
