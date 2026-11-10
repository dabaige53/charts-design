import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { format, parseISO } from "date-fns";
import { zhCN } from "date-fns/locale";
import type { DateRange } from "react-day-picker";
import { Toaster, toast } from "sonner";
import {
  ArrowDown,
  ArrowUp,
  Check,
  ChevronDown,
  Download,
  FileDown,
  Maximize2,
  PanelRight,
  Table2,
  Copy,
  RotateCcw,
  X,
  GripVertical,
  CalendarIcon,
  ImageDown,
  Search,
  BarChart3,
  MoreHorizontal,
} from "lucide-react";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  cn,
  MetricInfoIcon,
} from "./ui";
import { Input } from "./components/ui/input";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from "./components/ui/input-group";
import { Badge } from "./components/ui/badge";
import { Checkbox } from "./components/ui/checkbox";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "./components/ui/popover";
import {
  Command,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "./components/ui/command";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem,
} from "./components/ui/select";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from "./components/ui/dropdown-menu";
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldError,
} from "./components/ui/field";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./components/ui/tooltip";
import { ToggleGroup, ToggleGroupItem } from "./components/ui/toggle-group";
import { Calendar } from "./components/ui/calendar";
import { Alert, AlertDescription } from "./components/ui/alert";
import {
  Pagination as PaginationNav,
  PaginationContent,
  PaginationItem,
} from "./components/ui/pagination";
import { Skeleton } from "./components/ui/skeleton";

export type Choice = { value: string; label: string };
export type ActiveFilter = { id: string; label: string };
export type ChoicePage = {
  options: Choice[];
  hasMore: boolean;
  total?: number;
};
export type ChoiceLoader = (
  search: string,
  offset: number,
) => Promise<ChoicePage>;

export function ChoiceSelect({
  label,
  value,
  options,
  onChange,
  disabled = false,
  labelHidden = false,
}: {
  label: string;
  value: string;
  options: Choice[];
  onChange: (value: string) => void;
  disabled?: boolean;
  labelHidden?: boolean;
}) {
  const id = useId();
  return (
    <Field className={cn("w-auto", labelHidden ? "min-w-16" : "min-w-24")}>
      <FieldLabel htmlFor={id} className={labelHidden ? "sr-only" : undefined}>
        {label}
      </FieldLabel>
      <Select value={value} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue placeholder="请选择" />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            {options.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
    </Field>
  );
}

export function MultiSelect({
  label,
  options,
  value,
  onChange,
  loadOptions,
  disabled = false,
  labelHidden = false,
  single = false,
}: {
  label: string;
  options: Choice[];
  value: string[];
  onChange: (value: string[]) => void;
  loadOptions?: ChoiceLoader;
  disabled?: boolean;
  labelHidden?: boolean;
  single?: boolean;
}) {
  const [open, setOpen] = useState(false),
    [query, setQuery] = useState(""),
    [remote, setRemote] = useState<ChoicePage>({ options: [], hasMore: false });
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const sequence = useRef(0),
    id = useId();
  useEffect(() => {
    const request = ++sequence.current;
    if (!open || !loadOptions) return;
    setBusy(true);
    setError("");
    const timer = setTimeout(() => {
      void loadOptions(query, 0)
        .then((page) => {
          if (request === sequence.current) setRemote(page);
        })
        .catch((e) => {
          if (request === sequence.current) setError(String(e));
        })
        .finally(() => {
          if (request === sequence.current) setBusy(false);
        });
    }, 150);
    return () => {
      clearTimeout(timer);
      sequence.current++;
    };
  }, [open, query, loadOptions]);
  const shown = loadOptions
    ? remote.options
    : options.filter((o) =>
        o.label.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
      );
  const more = async () => {
    if (!loadOptions) return;
    const request = sequence.current;
    setBusy(true);
    setError("");
    try {
      const page = await loadOptions(query, remote.options.length);
      if (request === sequence.current)
        setRemote({ ...page, options: [...remote.options, ...page.options] });
    } catch (e) {
      if (request === sequence.current) setError(String(e));
    } finally {
      if (request === sequence.current) setBusy(false);
    }
  };
  const all = async () => {
    if (!loadOptions) {
      onChange(options.map((o) => o.value));
      return;
    }
    const request = sequence.current;
    setBusy(true);
    setError("");
    try {
      const ids: string[] = [];
      let page: ChoicePage;
      do {
        page = await loadOptions("", ids.length);
        if (request !== sequence.current) return;
        ids.push(...page.options.map((o) => o.value));
      } while (page.hasMore);
      onChange(ids);
    } catch (e) {
      if (request === sequence.current) setError(String(e));
    } finally {
      if (request === sequence.current) setBusy(false);
    }
  };
  return (
    <Field className="min-h-8 w-auto min-w-32 max-w-full shrink-0">
      <FieldLabel htmlFor={id} className={labelHidden ? "sr-only" : undefined}>
        {label}
      </FieldLabel>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            id={id}
            variant="outline"
            role="combobox"
            aria-expanded={open}
            disabled={disabled}
            className="min-w-0 justify-between"
          >
            {labelHidden && <span className="shrink-0 text-muted-foreground">{label}</span>}
            <span className="min-w-0 truncate">
              {value.length === 1
                ? [...options, ...remote.options].find((o) => o.value === value[0])?.label || "已选 1 项"
                : value.length
                  ? `已选 ${value.length} 项`
                  : "全部"}
            </span>
            <ChevronDown data-icon="inline-end" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-72 p-0">
          <Command shouldFilter={false}>
            <CommandInput
              aria-label={`搜索${label}`}
              placeholder="搜索选项"
              value={query}
              onValueChange={setQuery}
            />
            <div className="flex items-center justify-between px-2 py-1">
              {!single && <Button
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() => void all()}
              >
                全选
              </Button>}
              <span className="text-xs text-muted-foreground">
                已选 {value.length} 项
              </span>
              <Button
                variant="ghost"
                size="sm"
                disabled={!value.length}
                onClick={() => onChange([])}
              >
                清空
              </Button>
            </div>
            <CommandList aria-busy={busy}>
              {busy && !shown.length ? (
                <div className="p-3">
                  <Skeleton className="h-11 w-full" />
                </div>
              ) : (
                <CommandEmpty>没有匹配选项</CommandEmpty>
              )}
              <CommandGroup>
                {shown.map((o) => (
                  <CommandItem
                    key={o.value}
                    value={o.value}
                    aria-label={`${o.label}${value.includes(o.value) ? "，已选" : ""}`}
                    onSelect={() => {
                      onChange(single ? [o.value] : value.includes(o.value)
                        ? value.filter((v) => v !== o.value)
                        : [...value, o.value]);
                      if (single) setOpen(false);
                    }}
                  >
                    <Check
                      className={cn(
                        "size-4",
                        !value.includes(o.value) && "opacity-0",
                      )}
                    />
                    <span>{o.label}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
            {loadOptions && remote.hasMore && (
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() => void more()}
              >
                {busy ? "正在加载…" : "加载更多"}
              </Button>
            )}
          </Command>
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </PopoverContent>
      </Popover>
    </Field>
  );
}

export function ActiveFilters({
  items,
  onRemove,
  onClear,
  title = "已生效条件",
  showClear = true,
}: {
  items: ActiveFilter[];
  onRemove: (id: string) => void;
  onClear: () => void;
  title?: string;
  showClear?: boolean;
}) {
  return (
    <section className="flex flex-wrap items-center gap-2" aria-label={title}>
      <span className="text-xs text-muted-foreground">{title}</span>
      {items.length ? (
        items.map((item) => (
          <Badge key={item.id} variant="secondary">
            {item.label}
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={`移除${item.label}`}
              onClick={() => onRemove(item.id)}
            >
              <X />
            </Button>
          </Badge>
        ))
      ) : (
        <span className="text-xs text-muted-foreground">全部数据</span>
      )}
      {showClear && <Button
        variant="ghost"
        size="sm"
        disabled={!items.length}
        onClick={onClear}
      >
        清空全部
      </Button>}
    </section>
  );
}

export function RangeFilter({
  label,
  onApply,
  value,
  type = "number",
}: {
  label: string;
  onApply: (from: string, to: string) => void;
  value?: [string, string];
  type?: "number" | "text";
}) {
  const [from, setFrom] = useState(value?.[0] ?? ""),
    [to, setTo] = useState(value?.[1] ?? ""),
    [error, setError] = useState("");
  const id = useId();
  useEffect(() => {
    setFrom(value?.[0] ?? "");
    setTo(value?.[1] ?? "");
    setError("");
  }, [value?.[0], value?.[1]]);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (
          !!from !== !!to ||
          (from &&
            to &&
            (type === "number" ? Number(from) > Number(to) : from > to))
        ) {
          setError("请填写完整范围，起始值不得大于结束值。");
          return;
        }
        setError("");
        onApply(from, to);
      }}
    >
      <FieldGroup className="flex-row flex-wrap items-end gap-3">
        <Field className="w-36" data-invalid={!!error}>
          <FieldLabel htmlFor={id}>{label}起始</FieldLabel>
          <Input
            id={id}
            type={type}
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            aria-invalid={!!error}
          />
        </Field>
        <Field className="w-36" data-invalid={!!error}>
          <FieldLabel htmlFor={id + "-end"}>{label}结束</FieldLabel>
          <Input
            id={id + "-end"}
            type={type}
            value={to}
            onChange={(e) => setTo(e.target.value)}
            aria-invalid={!!error}
          />
        </Field>
        <Button type="submit" variant="outline">
          应用
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            setFrom("");
            setTo("");
            setError("");
            onApply("", "");
          }}
        >
          清空
        </Button>
      </FieldGroup>
      {error && <FieldError>{error}</FieldError>}
    </form>
  );
}

export function DateRangeFilter({
  label,
  value,
  onApply,
  labelHidden = false,
}: {
  label: string;
  value?: [string, string];
  onApply: (from: string, to: string) => void;
  labelHidden?: boolean;
}) {
  const [open, setOpen] = useState(false),
    [range, setRange] = useState<DateRange | undefined>();
  useEffect(() => {
    setRange(
      value?.[0]
        ? {
            from: parseISO(value[0]),
            to: value[1] ? parseISO(value[1]) : undefined,
          }
        : undefined,
    );
  }, [value?.[0], value?.[1]]);
  const id = useId();
  const today = new Date();
  const year = today.getFullYear(), month = today.getMonth(), day = today.getDate();
  const shortcuts = [
    { label: "近7天", from: new Date(year, month, day - 6), to: today },
    { label: "近30天", from: new Date(year, month, day - 29), to: today },
    { label: "本月", from: new Date(year, month, 1), to: new Date(year, month + 1, 0) },
    { label: "上月", from: new Date(year, month - 1, 1), to: new Date(year, month, 0) },
    { label: "本年", from: new Date(year, 0, 1), to: new Date(year, 11, 31) },
  ];
  return (
    <Field className="min-h-8 w-auto max-w-full shrink-0">
      <FieldLabel htmlFor={id} className={labelHidden ? "sr-only" : undefined}>
        {label}
      </FieldLabel>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button id={id} variant="outline" className="max-w-full">
            <CalendarIcon data-icon="inline-start" />
            {labelHidden && <span className="shrink-0 text-muted-foreground">{label}</span>}
            <span className="min-w-0 truncate">
              {value?.[0] ? `${value[0]} — ${value[1]}` : labelHidden ? "不限" : "选择日期范围"}
            </span>
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-80 max-w-[calc(100vw-2rem)] p-0" align="start">
          <div className="flex flex-wrap gap-1 border-b border-border p-2" aria-label="快捷日期范围">
            {shortcuts.map((shortcut) => (
              <Button
                key={shortcut.label}
                variant="ghost"
                size="xs"
                onClick={() => {
                  onApply(format(shortcut.from, "yyyy-MM-dd"), format(shortcut.to, "yyyy-MM-dd"));
                  setOpen(false);
                }}
              >
                {shortcut.label}
              </Button>
            ))}
          </div>
          <Calendar
            mode="range"
            locale={zhCN}
            selected={range}
            onSelect={setRange}
            numberOfMonths={1}
          />
          <div className="flex justify-end gap-2 p-3">
            <Button
              variant="ghost"
              onClick={() => {
                setRange(undefined);
                onApply("", "");
                setOpen(false);
              }}
            >
              清空
            </Button>
            <Button
              disabled={!range?.from || !range.to}
              onClick={() => {
                onApply(
                  format(range!.from!, "yyyy-MM-dd"),
                  format(range!.to!, "yyyy-MM-dd"),
                );
                setOpen(false);
              }}
            >
              应用
            </Button>
          </div>
        </PopoverContent>
      </Popover>
    </Field>
  );
}

export function IconAction({
  label,
  onClick,
  disabled = false,
  children,
  unavailable = "当前宿主未提供此操作",
  size = "icon-xs",
  variant = "ghost",
  pressed,
}: {
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  children: ReactNode;
  unavailable?: string;
  size?: "icon-xs" | "icon-sm";
  variant?: "ghost" | "outline" | "default";
  pressed?: boolean;
}) {
  const inactive = disabled || !onClick;
  return (
    <TooltipProvider delayDuration={250}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex" tabIndex={inactive ? 0 : undefined}>
            <Button
              variant={variant}
              size={size}
              aria-label={label}
              aria-pressed={pressed}
              disabled={inactive}
              onClick={onClick}
            >
              {children}
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>
          {inactive ? `${label}：${unavailable}` : label}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function ChartToolbar({
  chartType,
  onChartType,
  grain,
  onGrain,
  showTable,
  onToggle,
  onExport,
  onCopy,
  onImage,
  onFullscreen,
  onInfo,
}: {
  chartType?: string;
  onChartType?: (value: string) => void;
  grain?: string;
  onGrain?: (v: string) => void;
  showTable: boolean;
  onToggle: () => void;
  onExport?: () => void;
  onCopy?: () => void;
  onImage?: () => void;
  onFullscreen?: () => void;
  onInfo?: () => void;
}) {
  return (
    <div
      className="flex flex-nowrap items-center justify-end gap-0.5"
      aria-label="图表操作栏"
    >
      {chartType && onChartType && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-xs" aria-label="切换图表类型" title="切换图表类型">
              <BarChart3 />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuRadioGroup value={chartType} onValueChange={onChartType}>
              <DropdownMenuRadioItem value="c01">垂直柱状图</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="c02">横向条形图</DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
      <div className="flex shrink-0 items-center gap-0.5" role="group" aria-label="查看方式">
      {onGrain && (
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={grain}
          onValueChange={(v) => {
            if (v) onGrain(v);
          }}
          aria-label="时间粒度"
        >
          <ToggleGroupItem value="month">月度</ToggleGroupItem>
          <ToggleGroupItem value="quarter">季度</ToggleGroupItem>
        </ToggleGroup>
      )}
      <IconAction
        label={showTable ? "显示图表" : "显示数据表"}
        onClick={onToggle}
      >
        <Table2 />
      </IconAction>
      </div>
      <IconAction label="业务口径" onClick={onInfo}>
        <MetricInfoIcon />
      </IconAction>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-xs" aria-label="更多图表操作" title="更多图表操作">
            <MoreHorizontal />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem disabled={!onExport} onSelect={onExport}><FileDown />导出 CSV</DropdownMenuItem>
          <DropdownMenuItem disabled={!onImage} onSelect={onImage}><ImageDown />下载图片</DropdownMenuItem>
          <DropdownMenuItem disabled={!onCopy} onSelect={onCopy}><Copy />复制图表</DropdownMenuItem>
          <DropdownMenuItem disabled={!onFullscreen} onSelect={onFullscreen}><Maximize2 />全屏</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

export function TableToolbar({
  query,
  onQuery,
  onColumns,
  onExport,
}: {
  query: string;
  onQuery: (v: string) => void;
  onColumns: () => void;
  onExport?: () => void;
}) {
  const id = useId();
  return (
    <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2" role="toolbar" aria-label="表格操作">
      <Field className="w-40 min-w-0 max-w-full">
        <FieldLabel htmlFor={id} className="sr-only">
          搜索本表
        </FieldLabel>
        <InputGroup>
          <InputGroupAddon><Search /></InputGroupAddon>
          <InputGroupInput
            id={id}
            type="search"
            placeholder="搜索本表"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
          />
          {query && (
            <InputGroupAddon align="inline-end">
              <InputGroupButton size="icon-xs" aria-label="清空表内搜索" onClick={() => onQuery("")}>
                <X />
              </InputGroupButton>
            </InputGroupAddon>
          )}
        </InputGroup>
      </Field>
      <div className="flex shrink-0 items-center gap-1" role="group" aria-label="列配置与导出">
      <IconAction label="自定义列配置" onClick={onColumns} size="icon-sm">
        <PanelRight />
      </IconAction>
      <IconAction label="导出 CSV" onClick={onExport} size="icon-sm">
        <Download />
      </IconAction>
      </div>
    </div>
  );
}

function SortableColumn({
  column,
  checked,
  onToggle,
  onMove,
  first,
  last,
}: {
  column: Choice;
  checked: boolean;
  onToggle: () => void;
  onMove: (direction: number) => void;
  first: boolean;
  last: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, transition } =
    useSortable({ id: column.value });
  const id = useId();
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className="flex min-h-8 items-center gap-2 border-b border-border"
    >
      <Button
        variant="ghost"
        size="icon"
        {...attributes}
        {...listeners}
        aria-label={`拖动${column.label}，按空格开始键盘排序`}
      >
        <GripVertical />
      </Button>
      <Checkbox id={id} checked={checked} onCheckedChange={onToggle} />
      <label htmlFor={id} className="flex-1 text-sm">
        {column.label}
      </label>
      <Button
        variant="ghost"
        size="icon-sm"
        disabled={first}
        onClick={() => onMove(-1)}
        aria-label={`上移${column.label}`}
      >
        <ArrowUp />
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        disabled={last}
        onClick={() => onMove(1)}
        aria-label={`下移${column.label}`}
      >
        <ArrowDown />
      </Button>
    </div>
  );
}
export function ColumnSettings({
  columns,
  visible,
  onChange,
  onReset,
  order,
  onOrderChange,
}: {
  columns: Choice[];
  visible: string[];
  onChange: (ids: string[]) => void;
  onReset: () => void;
  order?: string[];
  onOrderChange?: (ids: string[]) => void;
}) {
  const ids = order ?? [
    ...visible,
    ...columns.map((c) => c.value).filter((id) => !visible.includes(id)),
  ];
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );
  const move = (from: number, to: number) => {
    if (to < 0 || to >= ids.length) return;
    const next = arrayMove(ids, from, to);
    if (onOrderChange) onOrderChange(next);
    else onChange(next.filter((id) => visible.includes(id)));
  };
  return (
    <section className="flex flex-col gap-3 p-4" aria-label="列配置">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          勾选显示列，拖动手柄调整顺序。
        </p>
        <Button variant="ghost" size="sm" onClick={onReset}>
          <RotateCcw data-icon="inline-start" />
          恢复默认
        </Button>
      </div>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={({ active, over }) => {
          if (over && active.id !== over.id)
            move(ids.indexOf(String(active.id)), ids.indexOf(String(over.id)));
        }}
      >
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          {ids.map((id, i) => {
            const column = columns.find((c) => c.value === id)!;
            return (
              <SortableColumn
                key={id}
                column={column}
                checked={visible.includes(id)}
                onToggle={() =>
                  onChange(
                    visible.includes(id)
                      ? visible.filter((v) => v !== id)
                      : [...visible, id],
                  )
                }
                onMove={(d) => move(i, i + d)}
                first={i === 0}
                last={i === ids.length - 1}
              />
            );
          })}
        </SortableContext>
      </DndContext>
    </section>
  );
}

export function Pagination({
  page,
  pages,
  pageSize,
  onChange,
}: {
  page: number;
  pages: number;
  pageSize: number;
  onChange: (page: number, size: number) => void;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 text-sm">
      <ChoiceSelect
        label="每页条数"
        labelHidden
        value={String(pageSize)}
        options={[...new Set([10, 20, 25, 50, 100, pageSize])]
          .sort((a, b) => a - b)
          .map((n) => ({ value: String(n), label: `${n} 条` }))}
        onChange={(v) => onChange(1, Number(v))}
      />
      <PaginationNav className="mx-0 w-auto" aria-label="数据分页">
        <PaginationContent>
          <PaginationItem>
            <Button
              variant="outline"
              disabled={page <= 1}
              onClick={() => onChange(1, pageSize)}
            >
              首页
            </Button>
          </PaginationItem>
          <PaginationItem>
            <Button
              variant="outline"
              disabled={page <= 1}
              onClick={() => onChange(page - 1, pageSize)}
            >
              上一页
            </Button>
          </PaginationItem>
          <PaginationItem>
            <span className="px-2" aria-live="polite">
              第 {page} / {pages} 页
            </span>
          </PaginationItem>
          <PaginationItem>
            <Button
              variant="outline"
              disabled={page >= pages}
              onClick={() => onChange(page + 1, pageSize)}
            >
              下一页
            </Button>
          </PaginationItem>
          <PaginationItem>
            <Button
              variant="outline"
              disabled={page >= pages}
              onClick={() => onChange(pages, pageSize)}
            >
              末页
            </Button>
          </PaginationItem>
        </PaginationContent>
      </PaginationNav>
    </div>
  );
}
export function SortControl({
  label,
  direction,
  onChange,
  align = "center",
}: {
  label: string;
  direction: "asc" | "desc" | null;
  onChange: (direction: "asc" | "desc") => void;
  align?: "left" | "center" | "right";
}) {
  return (
    <Button
      variant="ghost"
      size="xs"
      className={`relative w-full ${
        align === "right" ? "justify-end pl-5 pr-0 text-right"
          : align === "center" ? "justify-center px-5 text-center"
          : "justify-start pl-0 pr-5 text-left"
      }`}
      onClick={() => onChange(direction === "asc" ? "desc" : "asc")}
    >
      {label}
      {direction === "asc" ? (
        <ArrowUp className={`absolute size-3 ${align === "right" ? "left-0" : "right-0"}`} aria-hidden="true" />
      ) : direction === "desc" ? (
        <ArrowDown className={`absolute size-3 ${align === "right" ? "left-0" : "right-0"}`} aria-hidden="true" />
      ) : null}
    </Button>
  );
}
export function StatusBadge({ children }: { children: ReactNode }) {
  return <Badge variant="secondary">{children}</Badge>;
}
export function Toast({
  kind,
  children,
  onClose,
}: {
  kind: "success" | "info" | "warning";
  children: ReactNode;
  onClose: () => void;
}) {
  const id = useId();
  useEffect(() => {
    toast[kind](children, { id, duration: Infinity, onDismiss: onClose });
    return () => {
      toast.dismiss(id);
    };
  }, [id, kind, children]);
  return <Toaster position="bottom-right" closeButton />;
}
export function ExplanationDialog({
  open,
  onOpenChange,
  title,
  children,
}: {
  open: boolean;
  onOpenChange: (value: boolean) => void;
  title: string;
  children: ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>业务口径与计算方式</DialogDescription>
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  );
}
