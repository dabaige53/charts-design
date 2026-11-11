import React, {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { GridStack } from "gridstack";
import type { Document, Position } from "./types";
export function DashboardGrid({
  document: doc,
  editing,
  onLayoutChange,
  children,
}: {
  document: Document;
  editing: boolean;
  onLayoutChange: (p: Position[], bp: string) => void;
  children: (id: string) => React.ReactNode;
}) {
  const container = useRef<HTMLDivElement>(null),
    grid = useRef<GridStack | undefined>(undefined),
    callback = useRef(onLayoutChange),
    editingRef = useRef(editing),
    scheduleMeasure = useRef<(() => void) | undefined>(undefined),
    [bp, setBp] = useState("desktop");
  callback.current = onLayoutChange;
  editingRef.current = editing;
  useLayoutEffect(() => {
    const observer = new ResizeObserver(([entry]) =>
      setBp(
        entry.contentRect.width < 600
          ? "mobile"
          : entry.contentRect.width < 1000
            ? "tablet"
            : "desktop",
      ),
    );
    observer.observe(container.current!);
    return () => observer.disconnect();
  }, []);
  const layoutDraft = useMemo(
    () => new Map<string, Position[]>(),
    [doc.id],
  );
  useLayoutEffect(() => {
    if (!editing) layoutDraft.clear();
  }, [layoutDraft, editing, doc.revision]);
  const ids = Object.keys(doc.manifest.components).join("|"),
    positions = doc.manifest.layout[bp] || [],
    signature = JSON.stringify(positions);
  useLayoutEffect(() => {
    const node = container.current!,
      cols = bp === "mobile" ? 4 : bp === "tablet" ? 8 : 12;
    const instance = GridStack.init(
      {
        column: cols,
        cellHeight: 48,
        margin: 8,
        staticGrid: !editing,
        auto: false,
        handle: ".resize-handle",
        animate: false,
        float: false,
      },
      node,
    );
    grid.current = instance;
    instance.batchUpdate();
    Object.keys(doc.manifest.components).forEach((id, i) => {
      const el = [...node.children].find(
        (el) => (el as HTMLElement).dataset.widget === id,
      ) as HTMLElement;
      const position =
        (layoutDraft.get(bp) ?? positions).find((p) => p.id === id) || {
          id,
          x: 0,
          y: i * 8,
          w: cols,
          h: doc.manifest.components[id].kind === "table" ? 11 : 8,
        };
      instance.makeWidget(el, { ...position });
    });
    instance.batchUpdate(false);
    instance.on("change", () => {
      if (!editingRef.current) return;
      const next = instance.engine.nodes.map((n) => ({
        id: String(n.id),
        x: n.x!,
        y: n.y!,
        w: n.w!,
        h: n.h!,
      }));
      layoutDraft.set(bp, next);
      callback.current(next, bp);
    });
    let frame = 0;
    const tableItems = Object.entries(doc.manifest.components).flatMap(([id, component]) => {
      const position = positions.find((item) => item.id === id);
      if (component.kind !== "table" || (position && ![7, 11].includes(position.h))) return [];
      const element = [...node.children].find(
        (child) => (child as HTMLElement).dataset.widget === id,
      ) as HTMLElement | undefined;
      return element ? [element] : [];
    });
    const measureTables = () => {
      frame = 0;
      if (editingRef.current) return;
      const updates: { element: HTMLElement; height: number }[] = [];
      for (const item of tableItems) {
        const table = item.querySelector("table");
        const header = item.querySelector<HTMLElement>('[data-slot="card-header"]');
        const footer = item.querySelector<HTMLElement>("footer");
        const card = item.querySelector<HTMLElement>('[data-slot="card"]');
        if (!table || !header || !footer || !card) continue;
        const rows = [...table.querySelectorAll("tbody tr")].slice(0, 10);
        const tableHeader = table.querySelector<HTMLElement>("thead");
        const styles = getComputedStyle(card);
        const pixels = header.offsetHeight + (tableHeader?.offsetHeight || 0)
          + rows.reduce((height, row) => height + (row as HTMLElement).offsetHeight, 0)
          + footer.offsetHeight + parseFloat(styles.paddingTop) + parseFloat(styles.paddingBottom)
          + parseFloat(styles.rowGap) + 16;
        const height = Math.max(2, Math.ceil((pixels + 8) / 48));
        const gridItem = item as HTMLElement & { gridstackNode?: { h?: number } };
        if (gridItem.gridstackNode?.h !== height) updates.push({ element: item, height });
      }
      if (!updates.length) return;
      instance.batchUpdate();
      updates.forEach(({ element, height }) => instance.update(element, { h: height }));
      instance.batchUpdate(false);
    };
    const schedule = () => {
      if (tableItems.length && !frame) frame = requestAnimationFrame(measureTables);
    };
    const observer = new MutationObserver(schedule);
    tableItems.forEach((item) => observer.observe(item, { childList: true, subtree: true, characterData: true }));
    scheduleMeasure.current = schedule;
    schedule();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      scheduleMeasure.current = undefined;
      instance.offAll();
      instance.destroy(false);
      grid.current = undefined;
    };
  }, [ids, signature, bp, layoutDraft]);
  useEffect(() => {
    grid.current?.setStatic(!editing);
    if (!editing) scheduleMeasure.current?.();
  }, [editing]);
  return (
    <div ref={container} className="grid-stack">
      {Object.keys(doc.manifest.components).map((id) => (
        <div key={id} className="grid-stack-item" data-widget={id}>
          <div className="grid-stack-item-content">{children(id)}</div>
        </div>
      ))}
    </div>
  );
}
