import { useEffect, useId, useRef, useState } from "react";
import { isValid, parseISO } from "date-fns";
import { Check, Copy, ClipboardPaste } from "lucide-react";
import { Button } from "./ui";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "./components/ui/dialog";
import { Field, FieldLabel } from "./components/ui/field";
import { Textarea } from "./components/ui/textarea";
import type { Document, Filter } from "./types";

type FilterValue = string | number | boolean | null;

function parseParameters(text: string, filters: Filter[], doc: Document) {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw Error("内容格式不对。请重新复制筛选条件，再完整粘贴。");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
    throw Error("这不是复制出的筛选条件。请使用「复用筛选」里的「复制」。");

  const definitions = new Map(filters.map((filter) => [filter.id, filter]));
  const updates = new Map<string, FilterValue[]>(filters.map((filter) => [filter.id, []]));
  for (const [id, values] of Object.entries(parsed)) {
    const filter = definitions.get(id);
    if (!filter) throw Error(`此栏没有「${id}」这一项。请从同一个筛选栏复制条件。`);
    if (!Array.isArray(values)) throw Error(`「${filter.label}」的格式不对。请保留复制内容中的方括号。`);

    const types = filter.componentIds.map((componentId) => {
      const component = doc.manifest.components[componentId];
      const datasetId = component.datasetId ?? component.binding?.datasetId;
      return doc.manifest.datasets[datasetId]?.fields?.[filter.field]?.type;
    });
    if (!values.every((value) =>
      value === null ||
      (["string", "number", "boolean"].includes(typeof value) &&
        (typeof value !== "number" || Number.isFinite(value)) &&
        types.every((type) => !type || (type === "date" ? typeof value === "string" : type === typeof value))),
    )) throw Error(`「${filter.label}」的值格式不对。请重新复制筛选条件。`);

    if (filter.selectionMode === "single" && values.length > 1)
      throw Error(`「${filter.label}」最多选择一项。`);
    if (filter.op === "contains" && (values.length > 1 || values.some((value) => typeof value !== "string" || [...value].length > 1000)))
      throw Error(`「${filter.label}」只接受一项不超过 1000 字符的文本。`);
    if (filter.op === "range" && values.length &&
        (values.length !== 2 || values[0] === null || values[1] === null || values[0] > values[1]))
      throw Error(`「${filter.label}」需要填写完整范围，起始值不得大于结束值。`);
    if (filter.op === "range" && types.includes("date") && values.some((value) => !isValid(parseISO(value))))
      throw Error(`「${filter.label}」的日期无效。请使用年-月-日格式，例如 2026-07-01。`);
    updates.set(id, values);
  }
  for (const filter of filters) {
    if (filter.required && updates.get(filter.id)?.length !== 1)
      throw Error(`「${filter.label}」必须选择一项。`);
  }
  return updates;
}

export function FilterParameters({
  document: doc,
  filters,
  onApply,
}: {
  document: Document;
  filters: Filter[];
  onApply: (updates: ReadonlyMap<string, FilterValue[]>) => void;
}) {
  const [mode, setMode] = useState<"copy" | "apply" | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState<{ message: string } | null>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const id = useId();
  useEffect(() => {
    if (!status) return;
    const timeout = window.setTimeout(() => setStatus(null), 5000);
    return () => window.clearTimeout(timeout);
  }, [status]);
  const copy = async (button: HTMLButtonElement) => {
    const selected = filters.filter((filter) => filter.values.length);
    const json = JSON.stringify(Object.fromEntries(selected.map((filter) => [filter.id, filter.values])), null, 2);
    setStatus(null);
    try {
      await navigator.clipboard.writeText(json);
      setStatus({ message: selected.length ? "已复制，稍后可粘贴恢复。" : "已复制。粘贴后会清除此栏条件。" });
    } catch {
      opener.current = button;
      setText(json);
      setMode("copy");
    }
  };
  return (
    <>
      <div role="group" aria-label="复用筛选" className="relative max-w-full border border-border bg-muted/60 px-1 py-px sm:ml-auto">
        <div className="flex flex-wrap items-center gap-1">
          <span className="px-1.5 text-xs font-medium text-muted-foreground">复用筛选</span>
          <Button type="button" variant="ghost" size="sm" aria-label="复制筛选条件" onClick={(event) => void copy(event.currentTarget)}>
            <Copy data-icon="inline-start" />复制
          </Button>
          <Button type="button" variant="ghost" size="sm" aria-label="粘贴筛选条件" onClick={(event) => {
            opener.current = event.currentTarget;
            setText("");
            setError("");
            setStatus(null);
            setMode("apply");
          }}>
            <ClipboardPaste data-icon="inline-start" />粘贴
          </Button>
        </div>
        <div role="status" className="pointer-events-none absolute top-full left-0 z-10 mt-1.5 flex w-max max-w-[calc(100vw-4rem)] items-start gap-1.5 bg-popover px-2.5 py-2 text-xs leading-4 text-popover-foreground shadow-sm empty:sr-only sm:right-0 sm:left-auto">
          {status && <><Check aria-hidden="true" className="size-4 shrink-0" />{status.message}</>}
        </div>
      </div>
      <Dialog open={mode !== null} onOpenChange={(open) => { if (!open) setMode(null); }}>
        <DialogContent onCloseAutoFocus={(event) => {
          event.preventDefault();
          opener.current?.focus();
        }}>
          <DialogHeader>
            <DialogTitle>{mode === "copy" ? "复制筛选条件" : "粘贴筛选条件"}</DialogTitle>
            <DialogDescription>
              {mode === "copy"
                ? "无法自动复制。你可以选中并复制下方内容。"
                : "应用后会替换此栏的筛选条件；未列出的条件会清除。"}
            </DialogDescription>
          </DialogHeader>
          <form className="grid gap-4" onSubmit={(event) => {
            event.preventDefault();
            let updates;
            try {
              updates = parseParameters(text, filters, doc);
            } catch (error) {
              setError((error as Error).message);
              return;
            }
            const count = [...updates.values()].filter((values) => values.length).length;
            const hadSelection = filters.some((filter) => filter.values.length);
            onApply(updates);
            setStatus({ message: count
              ? `已应用 ${count} 项筛选条件。`
              : hadSelection ? "已清除此栏的筛选条件。" : "此栏没有需要清除的条件。" });
            setMode(null);
          }}>
            <Field data-invalid={mode === "apply" && !!error}>
              <FieldLabel htmlFor={id}>{mode === "copy" ? "要复制的内容" : "已复制的筛选条件"}</FieldLabel>
              <Textarea
                id={id}
                value={text}
                readOnly={mode === "copy"}
                placeholder={mode === "apply" ? "将复制的内容粘贴到这里" : undefined}
                aria-invalid={mode === "apply" && !!error}
                aria-describedby={mode === "apply" && error ? `${id}-error` : undefined}
                onChange={(event) => { setText(event.target.value); setError(""); }}
                onFocus={(event) => { if (mode === "copy") event.currentTarget.select(); }}
                className="h-40 overflow-auto font-mono"
              />
              {mode === "apply" && error && <p id={`${id}-error`} role="alert" className="text-sm text-destructive">{error}</p>}
            </Field>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setMode(null)}>{mode === "copy" ? "完成" : "取消"}</Button>
              {mode === "apply" && <Button type="submit">应用筛选</Button>}
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
