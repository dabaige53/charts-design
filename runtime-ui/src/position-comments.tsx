import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import {
  ArrowUp, Check, CheckCircle2, ChevronRight, MapPin, MessageSquareText,
  MousePointer2, Pencil, RotateCcw, ScanLine, Trash2, X,
} from "lucide-react";
import { Button } from "./ui";
import { Textarea } from "./components/ui/textarea";
import { Field, FieldLabel } from "./components/ui/field";
import { Tooltip, TooltipContent, TooltipTrigger } from "./components/ui/tooltip";
import type { Config, Document, Filter, ToolCall } from "./types";

type Rect = { x: number; y: number; width: number; height: number };
type Selection = {
  componentId: string | null;
  anchor: {
    scope: "component" | "text" | "page";
    kind: "element" | "area";
    quote: string;
    rect: Rect;
    occurrence?: number;
  };
};
type Draft = Selection & { id: string; text: string; editing?: string; original?: Config };
const clamp = (value: number) => Math.max(0, Math.min(1, value));

function CommentAction({ label, children, disabled, destructive = false, onClick }: {
  label: string;
  children: ReactNode;
  disabled: boolean;
  destructive?: boolean;
  onClick: () => void;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button type="button" variant="ghost" size="icon-sm" aria-label={label}
          disabled={disabled} onClick={onClick}
          className={`size-9 rounded-md text-muted-foreground max-sm:size-11 ${
            destructive ? "hover:bg-destructive/10 hover:text-destructive" : "hover:text-foreground"
          }`}>
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent data-annotation-ui side="bottom" sideOffset={6} className="z-[11020]">
        {label}
      </TooltipContent>
    </Tooltip>
  );
}

function textTargets(root: Element, quote: string) {
  return [root, ...root.querySelectorAll("*")].filter((element) =>
    !element.closest("[data-annotation-ui]") &&
    !["SCRIPT", "STYLE", "SVG", "CANVAS"].includes(element.tagName) &&
    element.textContent?.trim() === quote &&
    ![...element.children].some((child) => child.textContent?.trim() === quote),
  );
}

function selected(root: HTMLElement, target: Element, area?: Rect): Selection | null {
  const component = target.closest<HTMLElement>("[data-component-id]");
  const scope = component && root.contains(component) ? component : root;
  const bounds = scope.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return null;
  const box = area || target.getBoundingClientRect();
  const left = Math.max(bounds.left, box.x), top = Math.max(bounds.top, box.y);
  const right = Math.min(bounds.right, box.x + box.width), bottom = Math.min(bounds.bottom, box.y + box.height);
  if (right <= left || bottom <= top) return null;
  const text = (target.textContent || "").trim();
  const quote = !area && text.length <= 1000 ? text : "";
  const matches = quote ? textTargets(scope, quote) : [];
  return {
    componentId: component?.dataset.componentId || null,
    anchor: {
      scope: component ? "component" : quote ? "text" : "page",
      kind: area ? "area" : "element",
      quote,
      occurrence: Math.max(0, matches.findIndex((element) => element === target || target.contains(element))),
      rect: {
        x: clamp((left - bounds.left) / bounds.width),
        y: clamp((top - bounds.top) / bounds.height),
        width: clamp((right - left) / bounds.width),
        height: clamp((bottom - top) / bounds.height),
      },
    },
  };
}

function locate(root: HTMLElement, value: Selection): Rect | null {
  const anchor = value.anchor;
  if (!anchor) return null;
  const scope = value.componentId
    ? root.querySelector<HTMLElement>(`[data-component-id="${CSS.escape(value.componentId)}"]`)
    : root;
  if (!scope) return null;
  if (anchor.kind === "element" && anchor.quote) {
    const element = textTargets(scope, anchor.quote)[anchor.occurrence || 0];
    if (!element) return null;
    const box = element.getBoundingClientRect();
    return { x: box.x, y: box.y, width: box.width, height: box.height };
  }
  const box = scope.getBoundingClientRect(), rect = anchor.rect;
  return { x: box.x + box.width * rect.x, y: box.y + box.height * rect.y,
    width: box.width * rect.width, height: box.height * rect.height };
}

export function PositionComments({
  document: doc, root, active, onActiveChange, onActivityChange, call, readOnly,
  filters, projectRoot, onNotesChange,
}: {
  document: Document;
  root: RefObject<HTMLDivElement | null>;
  active: boolean;
  onActiveChange: (value: boolean) => void;
  onActivityChange: (value: boolean) => void;
  call: ToolCall;
  readOnly: boolean;
  filters: Filter[];
  projectRoot?: string | null;
  onNotesChange: (notes: Config[]) => void;
}) {
  const [notes, setNotes] = useState<Config[]>(doc.manifest.annotations || []);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [listOpen, setListOpen] = useState(false), [openId, setOpenId] = useState<string | null>(null);
  const [replies, setReplies] = useState<Record<string, string>>({});
  const [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const [hover, setHover] = useState<Rect | null>(null), [dragRect, setDragRect] = useState<Rect | null>(null);
  const [positions, setPositions] = useState<Record<string, Rect>>({});
  const [screen, setScreen] = useState({ width: window.innerWidth, height: window.innerHeight });
  const [status, setStatus] = useState("open");
  const [hydrated, setHydrated] = useState(false);
  const draftRef = useRef(draft), busyRef = useRef(false), reanchor = useRef<Config | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const replyIds = useRef<Record<string, { text: string; id: string }>>({});
  const key = `charts-position-draft:${JSON.stringify([projectRoot || location.pathname, doc.id, readOnly])}`;
  const reply = openId ? replies[openId] || "" : "";
  const setReply = (text: string) => {
    if (!openId) return;
    setReplies((previous) => {
      const next = { ...previous };
      if (text) next[openId] = text;
      else delete next[openId];
      return next;
    });
  };
  const picking = active && !readOnly && !openId && !listOpen;
  const interacting = active || busy;
  draftRef.current = draft;

  useEffect(() => {
    if (!active || busy) return;
    let live = true;
    const load = () => {
      if (document.visibilityState !== "visible") return;
      void call("dashboard_annotations", { dashboardId: doc.id }).then((value) => {
        if (live) setNotes(value.annotations);
      }).catch((failure) => { if (live) setError(String(failure)); });
    };
    load();
    document.addEventListener("visibilitychange", load);
    return () => {
      live = false;
      document.removeEventListener("visibilitychange", load);
    };
  }, [call, doc.id, active, busy]);

  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(key);
      if (saved) {
        const value = JSON.parse(saved);
        const candidate = value.draft;
        if (candidate) {
          const rect = candidate.anchor?.rect;
          if (typeof candidate.id !== "string" || typeof candidate.text !== "string" ||
            !(candidate.componentId === null || typeof candidate.componentId === "string") ||
            typeof candidate.anchor?.quote !== "string" ||
            !["component", "page", "text"].includes(candidate.anchor?.scope) ||
            !["element", "area"].includes(candidate.anchor?.kind) ||
            !rect || !["x", "y", "width", "height"].every((name) =>
              Number.isFinite(rect[name]) && rect[name] >= 0 && rect[name] <= 1))
            throw Error("批注草稿格式已变化");
          setDraft(candidate);
        }
        if (value.replies && typeof value.replies === "object" && !Array.isArray(value.replies) &&
          Object.values(value.replies).every((text) => typeof text === "string"))
          setReplies(value.replies);
      }
    } catch {
      setError("无法读取批注草稿；输入内容将只保留在当前页面。");
    }
    setHydrated(true);
  }, [key]);
  useEffect(() => {
    if (!hydrated) return;
    try {
      if (draft || Object.keys(replies).length) sessionStorage.setItem(key, JSON.stringify({ draft, replies }));
      else sessionStorage.removeItem(key);
    } catch {
      setError("无法保存本地草稿，请在离开页面前提交批注。");
    }
  }, [draft, replies, key, hydrated]);
  useEffect(() => {
    onActivityChange(interacting);
    return () => onActivityChange(false);
  }, [interacting, onActivityChange]);
  useEffect(() => {
    if (active && readOnly) setListOpen(true);
    if (!active) {
      setOpenId(null);
      setListOpen(false);
      setHover(null);
      setDragRect(null);
      reanchor.current = null;
    }
  }, [active, readOnly]);
  useEffect(() => {
    if (picking && draft) input.current?.focus({ preventScroll: true });
  }, [picking, draft?.id, draft?.anchor]);
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if (event.isComposing || event.defaultPrevented || busyRef.current) return;
      if (event.key === "Escape" && active) {
        event.preventDefault();
        onActiveChange(false);
        return;
      }
      if (busyRef.current || event.code !== "KeyC" || event.repeat || event.metaKey || event.ctrlKey || event.altKey ||
        !(event.target instanceof Element) ||
        event.target.closest("input, textarea, select, [contenteditable], [role=dialog], [role=combobox], [data-annotation-ui]")) return;
      event.preventDefault();
      onActiveChange(!active);
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, [active, onActiveChange]);

  useEffect(() => {
    const page = root.current;
    if (!page || !active) return;
    let frame = 0;
    const measure = () => {
      const next: Record<string, Rect> = {};
      for (const note of notes) {
        if (!note.anchor) continue;
        const rect = locate(page, note as Selection);
        if (rect) next[note.id] = rect;
      }
      if (draft) {
        const rect = locate(page, draft);
        if (rect) next.draft = rect;
      }
      setPositions(next);
      setScreen({ width: window.innerWidth, height: window.innerHeight });
    };
    const schedule = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); };
    const resize = new ResizeObserver(schedule), mutation = new MutationObserver(schedule);
    resize.observe(page);
    page.querySelectorAll("[data-component-id]").forEach((element) => resize.observe(element));
    mutation.observe(page, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["style"] });
    window.addEventListener("scroll", schedule, true);
    window.addEventListener("resize", schedule);
    schedule();
    return () => {
      cancelAnimationFrame(frame); resize.disconnect(); mutation.disconnect();
      window.removeEventListener("scroll", schedule, true); window.removeEventListener("resize", schedule);
    };
  }, [active, notes, draft, root]);

  useEffect(() => {
    const page = root.current;
    if (!page || !picking) return;
    const previousTouchAction = page.style.touchAction;
    page.style.touchAction = "none";
    page.setAttribute("data-annotation-picking", "");
    let drag: { x: number; y: number; target: Element; moved: boolean } | null = null;
    const ignore = (element: Element) => !!element.closest("[data-annotation-ui]");
    const down = (event: PointerEvent) => {
      if (event.button !== 0 || busyRef.current || !(event.target instanceof Element) || ignore(event.target)) return;
      event.preventDefault(); event.stopPropagation();
      drag = { x: event.clientX, y: event.clientY, target: event.target, moved: false };
    };
    const move = (event: PointerEvent) => {
      if (drag) {
        drag.moved ||= Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 6;
        if (drag.moved) setDragRect({ x: Math.min(drag.x, event.clientX), y: Math.min(drag.y, event.clientY),
          width: Math.abs(event.clientX - drag.x), height: Math.abs(event.clientY - drag.y) });
      } else if (event.target instanceof Element && page.contains(event.target) && !ignore(event.target)) {
        const box = event.target.getBoundingClientRect();
        setHover({ x: box.x, y: box.y, width: box.width, height: box.height });
      } else setHover(null);
    };
    const choose = (target: Element, area?: Rect) => {
      const selection = selected(page, target, area);
      if (!selection) return;
      const previous = draftRef.current;
      const existing = reanchor.current || previous?.original;
      reanchor.current = null;
      setDraft({ ...selection, id: existing?.id || draftRef.current?.id || `note-${crypto.randomUUID()}`,
        text: previous?.text ?? existing?.text ?? "",
        ...(existing ? { editing: existing.id, original: existing } : {}) });
      setListOpen(false); setOpenId(null); setError(""); setHover(null);
    };
    const up = (event: PointerEvent) => {
      if (!drag) return;
      const current = drag;
      drag = null;
      event.preventDefault(); event.stopPropagation();
      if (current.moved) {
        const area = { x: Math.min(current.x, event.clientX), y: Math.min(current.y, event.clientY),
          width: Math.abs(current.x - event.clientX), height: Math.abs(current.y - event.clientY) };
        const end = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-component-id]");
        const start = current.target.closest("[data-component-id]");
        choose(start && start === end ? current.target : page, area);
      } else choose(current.target);
      setDragRect(null);
    };
    const cancel = () => { drag = null; setDragRect(null); };
    const click = (event: Event) => {
      if (event.target instanceof Element && !ignore(event.target)) {
        event.preventDefault(); event.stopPropagation();
      }
    };
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Enter" && event.target instanceof Element && page.contains(event.target) && !ignore(event.target)) {
        event.preventDefault(); event.stopPropagation(); choose(event.target);
      }
    };
    page.addEventListener("pointerdown", down, true);
    page.addEventListener("click", click, true);
    window.addEventListener("pointermove", move, true);
    window.addEventListener("pointerup", up, true);
    window.addEventListener("pointercancel", cancel);
    window.addEventListener("blur", cancel);
    window.addEventListener("keydown", keyboard, true);
    return () => {
      page.removeEventListener("pointerdown", down, true); page.removeEventListener("click", click, true);
      window.removeEventListener("pointermove", move, true); window.removeEventListener("pointerup", up, true);
      window.removeEventListener("pointercancel", cancel); window.removeEventListener("keydown", keyboard, true);
      window.removeEventListener("blur", cancel);
      page.style.touchAction = previousTouchAction;
      page.removeAttribute("data-annotation-picking");
    };
  }, [picking, root]);

  const write = async (change: (current: Config[]) => Config[]) => {
    if (readOnly || busyRef.current) return false;
    busyRef.current = true; setBusy(true); setError("");
    try {
      const latest = await call("dashboard_annotations", { dashboardId: doc.id });
      if (doc.progressive && latest.independentSave !== true)
        throw Error("批注服务需要重启 MCP 后更新；当前输入已保留。");
      const value = change(latest.annotations);
      const result = await call("dashboard_patch", {
        dashboardId: doc.id, expectedRevision: latest.revision,
        ...(doc.progressive ? { expectedAnnotations: latest.annotations } : {}),
        operations: [{ op: "set_annotations", value }],
      });
      const saved = result.document.manifest.annotations;
      setNotes(saved); onNotesChange(saved);
      return true;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
      return false;
    } finally { busyRef.current = false; setBusy(false); }
  };
  const submit = async () => {
    if (!draft || !draft.text.trim() || !positions.draft) return;
    const saved = await write((current) => {
      if (draft.editing) {
        const existing = current.find((note) => note.id === draft.editing);
        if (existing && existing.text === draft.text.trim() && existing.componentId === draft.componentId &&
          JSON.stringify(existing.anchor) === JSON.stringify(draft.anchor)) return current;
        if (JSON.stringify(existing) !== JSON.stringify(draft.original))
          throw Error("这条批注已更新，请从列表重新打开；当前输入已保留。");
        return current.map((note) => note.id === draft.editing
          ? { ...note, text: draft.text.trim(), componentId: draft.componentId, anchor: draft.anchor } : note);
      }
      const existing = current.find((note) => note.id === draft.id);
      if (existing) {
        if (existing.text === draft.text.trim() && existing.componentId === draft.componentId &&
          JSON.stringify(existing.anchor) === JSON.stringify(draft.anchor)) return current;
        throw Error("这条批注已更新；输入内容已保留，请从列表重新打开。");
      }
      return [...current, { id: draft.id, componentId: draft.componentId, anchor: draft.anchor,
        text: draft.text.trim(), createdAt: new Date().toISOString(),
        view: { revision: doc.revision, filters } }];
    });
    if (saved) { setDraft(null); setError(""); }
  };
  const current = notes.find((note) => note.id === openId);
  const submitReply = async () => {
    if (!current || !reply.trim()) return;
    if (replyIds.current[current.id]?.text !== reply.trim())
      replyIds.current[current.id] = { text: reply.trim(), id: crypto.randomUUID() };
    const response = replyIds.current[current.id];
    const saved = await write((items) => {
      if (!items.some((note) => note.id === current.id))
        throw Error("批注已被删除；当前回复已保留。");
      return items.map((note) => {
        if (note.id !== current.id) return note;
        if ((note.replies || []).some((item: Config) => item.id === response.id)) return note;
        if (note.status === "resolved") throw Error("批注已解决，请先重新打开再回复。");
        return { ...note, replies: [...(note.replies || []), {
          id: response.id, text: response.text, createdAt: new Date().toISOString(),
        }] };
      });
    });
    if (saved) setReply("");
  };
  const selectedRect = (picking ? dragRect || positions.draft || hover : null) ||
    (openId ? positions[openId] : null);
  const anchor = (picking ? positions.draft : null) || (openId ? positions[openId] : null);
  const width = Math.min(340, screen.width - 24);
  const maxPanelHeight = Math.min(560, screen.height - 96);
  const panelStyle = screen.width < 640
    ? { left: 12, right: 12, bottom: 64, maxHeight: "calc(100dvh - 96px)" }
    : { left: Math.max(12, Math.min(screen.width - width - 12, anchor ? anchor.x + anchor.width + 12 : screen.width - width - 16)),
        top: Math.max(12, Math.min(screen.height - maxPanelHeight - 16, anchor?.y || 76)),
        width, maxHeight: maxPanelHeight };
  const showComposer = picking ? draft : null;
  const showPanel = !!showComposer || !!current || listOpen || (active && !!error);
  const visibleNotes = notes.filter((note) => status === "all" || (note.status === "resolved" ? status === "resolved" : status === "open"));
  const locationLabel = (note: Config) => note.componentId ? doc.manifest.components[note.componentId]?.title || "组件已移除" : "页面位置";

  if (!active) return null;

  return createPortal(
    <div data-annotation-ui className="screen-only pointer-events-none fixed inset-0 z-[11000]">
      {selectedRect && <div className="fixed border-2 border-primary bg-primary/5" style={{
        left: selectedRect.x, top: selectedRect.y, width: selectedRect.width, height: selectedRect.height,
      }} />}
      {notes.map((note, index) => {
        const box = positions[note.id];
        if (!box || box.y + box.height < 0 || box.y > screen.height ||
          (note.status === "resolved" && note.id !== openId)) return null;
        return <button key={note.id} type="button" aria-label={`打开批注 ${index + 1}：${note.text.slice(0, 60)}`}
          className="pointer-events-auto fixed flex size-8 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          style={{ left: Math.min(screen.width - 36, Math.max(4, box.x + box.width - 16)), top: box.y - 12 }}
          disabled={busy}
          onClick={() => { setOpenId(note.id); setListOpen(false); setError(""); }}>{index + 1}</button>;
      })}
      {(active || listOpen || current || draft || error || Object.keys(replies).length > 0) && (
        <div className="pointer-events-auto fixed bottom-4 left-1/2 flex max-w-[calc(100vw-24px)] -translate-x-1/2 flex-wrap items-center gap-2 border border-border bg-popover px-3 py-2 text-xs shadow-md">
          {picking && <><MousePointer2 className="size-4" /><span>点击元素或拖动框选，再输入批注</span></>}
          {!picking && draft && <Button variant="ghost" size="sm" onClick={() => {
            setOpenId(null); setListOpen(false);
          }}>继续未提交批注</Button>}
          {!current && Object.keys(replies).length > 0 && <Button variant="ghost" size="sm" onClick={() => {
            setListOpen(false); setOpenId(Object.keys(replies)[0]);
          }}>继续未提交回复</Button>}
          {!current && Object.keys(replies).length > 0 && <Button variant="ghost" size="sm" onClick={() => setReplies({})}>丢弃未提交回复</Button>}
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => { setListOpen(!listOpen); setOpenId(null); }}>批注列表（{notes.length}）</Button>
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => {
            onActiveChange(false); setListOpen(false); setOpenId(null); setHover(null);
          }}>退出批注</Button>
        </div>
      )}
      {showPanel && (
        <section role="dialog" aria-labelledby="position-comment-title" aria-busy={busy}
          className="pointer-events-auto fixed flex flex-col overflow-hidden rounded-xl bg-popover text-popover-foreground shadow-xl"
          style={panelStyle}>
          <div className="flex shrink-0 items-center gap-3 border-b border-border px-4 py-2.5">
            <MessageSquareText aria-hidden="true" className="size-4 shrink-0 text-primary" />
            <h2 id="position-comment-title" className="min-w-0 flex-1 text-sm font-semibold">
              {showComposer ? "位置批注" : current ? `批注 ${notes.indexOf(current) + 1}` : "批注列表"}
            </h2>
            {current && !showComposer && (
              <span className={`inline-flex shrink-0 items-center gap-1 rounded px-2 py-1 text-xs font-normal ${
                current.status === "resolved" ? "bg-muted text-muted-foreground" : "bg-primary/10 text-primary"
              }`}>
                {current.status === "resolved" && <CheckCircle2 aria-hidden="true" className="size-3" />}
                {current.status === "resolved" ? "已解决" : "未解决"}
              </span>
            )}
            <CommentAction label="收起批注面板" disabled={busy} onClick={() => {
                if (showComposer) onActiveChange(false);
                else { setListOpen(false); setOpenId(null); }
              }}>
              <X aria-hidden="true" className="size-4" />
            </CommentAction>
          </div>
          {!showComposer && current && !readOnly && (
            <div role="toolbar" aria-label="批注操作"
              className="flex shrink-0 items-center justify-between gap-2 border-b border-border px-3 py-1">
              <div className="flex items-center gap-1">
                <CommentAction label="修改批注" disabled={busy} onClick={() => {
                  if (positions[current.id] && current.anchor) {
                    setDraft({ componentId: current.componentId, anchor: current.anchor, id: current.id,
                      text: current.text, editing: current.id, original: current });
                    onActiveChange(true); setOpenId(null);
                  } else { reanchor.current = current; onActiveChange(true); setOpenId(null); }
                }}><Pencil aria-hidden="true" className="size-4" /></CommentAction>
                <CommentAction label="重新标记位置" disabled={busy} onClick={() => {
                  reanchor.current = current; setOpenId(null); onActiveChange(true);
                }}><ScanLine aria-hidden="true" className="size-4" /></CommentAction>
                <CommentAction label="删除批注" destructive disabled={busy} onClick={() => {
                  void write((items) => items.filter((note) => note.id !== current.id)).then((saved) => {
                    if (saved) { setReply(""); setOpenId(null); }
                  });
                }}><Trash2 aria-hidden="true" className="size-4" /></CommentAction>
              </div>
              <Button type="button" variant="ghost" size="sm" disabled={busy}
                className="h-9 gap-1.5 rounded-md text-xs font-medium text-muted-foreground hover:text-primary max-sm:h-11"
                onClick={() => void write((items) => items.map((note) =>
                  note.id === current.id ? { ...note, status: note.status === "resolved" ? "open" : "resolved" } : note))}>
                {current.status === "resolved"
                  ? <RotateCcw aria-hidden="true" className="size-3.5" />
                  : <Check aria-hidden="true" className="size-3.5" />}
                {current.status === "resolved" ? "重新打开" : "标记已解决"}
              </Button>
            </div>
          )}
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
            {error && <p role="alert" className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
            {showComposer && <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
              <div className="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
                <MapPin aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
                <span>{locationLabel(showComposer)}{showComposer.anchor.kind === "area" ? " · 框选区域" : ""}</span>
              </div>
              {showComposer.anchor.quote && <blockquote className="max-h-20 overflow-auto rounded-md bg-muted p-3 text-xs leading-relaxed text-muted-foreground">{showComposer.anchor.quote}</blockquote>}
              {!positions.draft && <p role="status" className="text-sm text-destructive">所选位置已变化，请在页面上重新标记；输入内容已保留。</p>}
              <Field>
                <FieldLabel htmlFor="position-comment-text" className="text-xs font-medium">批注内容</FieldLabel>
                <Textarea ref={input} id="position-comment-text" autoFocus maxLength={4000}
                  value={showComposer.text} disabled={busy} placeholder="描述这个位置需要调整的内容…"
                  className="min-h-24 max-h-48 rounded-md border border-input bg-background px-3 py-2 text-sm leading-relaxed focus-visible:ring-2 focus-visible:ring-ring/20"
                  onChange={(event) => setDraft({ ...showComposer, text: event.target.value })}
                  onKeyDown={(event) => {
                    if (!event.nativeEvent.isComposing && (event.metaKey || event.ctrlKey) && event.key === "Enter") {
                      event.preventDefault(); void submit();
                    }
                  }} />
              </Field>
              <div className="flex justify-end gap-2">
                <Button type="button" variant="ghost" disabled={busy} onClick={() => { setDraft(null); setError(""); }}>取消</Button>
                <Button type="submit" className="gap-1.5" disabled={busy || !showComposer.text.trim() || !positions.draft}>
                  <ArrowUp aria-hidden="true" className="size-3.5" />{busy ? "正在保存…" : "提交批注"}
                </Button>
              </div>
            </form>}
            {!showComposer && current && (
              <>
                <div className="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
                  <MapPin aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
                  <span className="break-words">{locationLabel(current)}{!positions[current.id] ? " · 位置失效或尚未记录" : ""}</span>
                </div>
                <p className="whitespace-pre-wrap break-words text-sm font-normal leading-relaxed">{current.text}</p>
                {!!current.replies?.length && (
                  <div className="space-y-3 border-t border-border pt-4">
                    <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                      <MessageSquareText aria-hidden="true" className="size-3.5" />回复 {current.replies.length}
                    </p>
                    {current.replies.map((item: Config) => (
                      <p key={item.id} className="whitespace-pre-wrap break-words text-sm font-normal leading-relaxed">{item.text}</p>
                    ))}
                  </div>
                )}
              </>
            )}
            {!showComposer && listOpen && !current && <>
              <div role="group" className="flex gap-1" aria-label="批注状态">
                {([["open", "未解决"], ["resolved", "已解决"], ["all", "全部"]] as const).map(([value, label]) =>
                  <Button key={value} size="sm" aria-pressed={status === value}
                    variant={status === value ? "secondary" : "ghost"} onClick={() => setStatus(value)}>{label}</Button>)}
              </div>
              <div className="divide-y divide-border">
                {visibleNotes.length ? visibleNotes.map((note) => <button key={note.id} type="button"
                  className="flex w-full items-start gap-3 rounded-md p-3 text-left hover:bg-muted focus-visible:outline-2 focus-visible:outline-primary"
                  onClick={() => {
                    const page = root.current;
                    const target = note.componentId ? page?.querySelector(`[data-component-id="${CSS.escape(note.componentId)}"]`) : page;
                    target?.scrollIntoView({ block: "center", behavior: "smooth" });
                    setOpenId(note.id); setListOpen(false);
                  }}>
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-medium tabular-nums text-primary">{notes.indexOf(note) + 1}</span>
                  <span className="min-w-0 flex-1 space-y-1">
                    <span className="block text-xs text-muted-foreground">{locationLabel(note)}{!positions[note.id] ? " · 位置未记录或已失效" : ""}</span>
                    <span className="line-clamp-2 whitespace-pre-wrap break-words text-sm font-normal leading-relaxed">{note.text}</span>
                  </span>
                  <ChevronRight aria-hidden="true" className="mt-1 size-3.5 shrink-0 text-muted-foreground" />
                </button>) : <p className="py-4 text-sm text-muted-foreground">暂无此状态的批注。</p>}
              </div>
            </>}
          </div>
          {!showComposer && current && !readOnly && (
            current.status === "resolved" ? (
              <p className="flex shrink-0 items-center gap-2 border-t border-border bg-muted/40 px-4 py-3 text-xs text-muted-foreground">
                <CheckCircle2 aria-hidden="true" className="size-3.5 shrink-0" />已解决，重新打开后可继续回复。
              </p>
            ) : (
              <form className="shrink-0 space-y-3 border-t border-border bg-muted/40 p-4"
                onSubmit={(event) => { event.preventDefault(); void submitReply(); }}>
                <Field>
                  <FieldLabel htmlFor="position-comment-reply" className="text-xs font-medium">回复</FieldLabel>
                  <Textarea id="position-comment-reply" maxLength={4000} value={reply} disabled={busy}
                    placeholder="输入回复…"
                    className="min-h-20 max-h-32 rounded-md border border-input bg-background px-3 py-2 text-sm leading-relaxed focus-visible:ring-2 focus-visible:ring-ring/20"
                    onChange={(event) => setReply(event.target.value)}
                    onKeyDown={(event) => {
                      if (!event.nativeEvent.isComposing && (event.metaKey || event.ctrlKey) && event.key === "Enter") {
                        event.preventDefault(); event.currentTarget.form?.requestSubmit();
                      }
                    }} />
                </Field>
                <div className="flex justify-end gap-2">
                  {reply && <Button type="button" variant="ghost" disabled={busy} onClick={() => setReply("")}>取消回复</Button>}
                  <Button type="submit" disabled={busy || !reply.trim()} className="gap-1.5">
                    <ArrowUp aria-hidden="true" className="size-3.5" />{busy ? "正在保存…" : "提交回复"}
                  </Button>
                </div>
              </form>
            )
          )}
        </section>
      )}
    </div>,
    window.document.body,
  );
}
