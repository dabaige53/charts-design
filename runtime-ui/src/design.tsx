// Design-only data adapter. Production entries never import this file or fixtures.
import { useId, useMemo, useState } from "react";
import examples from "../fixtures/examples.json";
import chartExamples from "../fixtures/charts.json";
import chartCatalog from "../fixtures/chart-catalog.json";
import { chartOption, EChartSurface } from "./chart";
import { MetricCard } from "./metric";
import { DataTable } from "./table";
import { Button, Card, CardHeader, CardTitle, CardDescription, CardContent, MetricInfoIcon } from "./ui";
import { Input } from "./components/ui/input";
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldSet,
  FieldLegend,
} from "./components/ui/field";
import { Checkbox } from "./components/ui/checkbox";
import { Alert, AlertTitle, AlertDescription } from "./components/ui/alert";
import { Empty, EmptyHeader, EmptyTitle } from "./components/ui/empty";
import { Info, SlidersHorizontal } from "lucide-react";
import {
  ActiveFilters,
  ChartToolbar,
  ChoiceSelect,
  ColumnSettings,
  DateRangeFilter,
  ExplanationDialog,
  IconAction,
  MultiSelect,
  Pagination,
  RangeFilter,
  SortControl,
  StatusBadge,
  TableToolbar,
  Toast,
} from "./controls";
import { browserDownload, csvBlob } from "./host";
import type { ActiveFilter } from "./controls";
import type { Config, Document, TableState } from "./types";
export { Button, Card };
export { Button as Buttons, Card as Cards };
export {
  CardHeader,
  CardTitle,
  CardDescription,
  CardAction,
  CardContent,
  CardFooter,
} from "./ui";
export { DataTable as DataTables };
export { Input as TextInputs };
export { Checkbox as Checkboxes } from "./components/ui/checkbox";
export {
  ChoiceSelect as Select,
  DateRangeFilter as DatePicker,
  ActiveFilters as Tags,
  StatusBadge as Badges,
  IconAction as Tooltips,
  ExplanationDialog as Modals,
} from "./controls";
export { Alert as Alerts } from "./components/ui/alert";
export {
  ActiveFilters,
  ChartToolbar,
  ChoiceSelect,
  ColumnSettings,
  DateRangeFilter,
  ExplanationDialog,
  MultiSelect,
  Pagination,
  RangeFilter,
  SortControl,
  StatusBadge,
  TableToolbar,
  Toast,
} from "./controls";
const charts = chartExamples as Record<string, Config>;
export function ChartTile({ code }: { code: string }) {
  const c = charts[code],
    info = chartCatalog.find((item) => item.id === code);
  const option = useMemo(() => chartOption(c), [c]);
  if (!info) throw Error(`图表目录缺少 ${code} 的介绍`);
  return (
    <Card className="min-h-[360px]">
      <CardHeader>
        <CardTitle>{info.nameZh}</CardTitle>
        <CardDescription>{info.bestFor}</CardDescription>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col">
      <EChartSurface
        option={option}
        label={info.nameZh}
        className="min-h-[250px] w-full flex-1"
      />
      </CardContent>
    </Card>
  );
}
export function MetricTile({ code }: { code: string }) {
  const item = (examples.metrics as Config)[code];
  return (
    <Card size="sm" className="min-h-[320px]">
      <CardHeader>
        <CardTitle>{item.name}</CardTitle>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col">
      <MetricCard config={{ ...item.example, type: code }} />
      </CardContent>
    </Card>
  );
}
const hubs = [
  { value: "east", label: "华东基地" },
  { value: "south", label: "华南基地" },
  { value: "north", label: "北方基地" },
  { value: "west", label: "西南基地" },
];
const cols = [
  { value: "route", label: "航线" },
  { value: "region", label: "大区" },
  { value: "owner", label: "负责人" },
  { value: "revenue", label: "收入" },
  { value: "rate", label: "达成率" },
];
export function ControlPreview({ kind }: { kind: string }) {
  const id = useId();
  const [moreFilters, setMoreFilters] = useState(false);
  const [selected, setSelected] = useState<string[]>(["east"]),
    [filters, setFilters] = useState<ActiveFilter[]>([]);
  const [season, setSeason] = useState("2026夏秋航季"),
    [fleet, setFleet] = useState("全部机型"),
    [route, setRoute] = useState("全部航线"),
    [query, setQuery] = useState("");
  const [grain, setGrain] = useState("month"),
    [table, setTable] = useState(false),
    [visible, setVisible] = useState(cols.map((c) => c.value)),
    [page, setPage] = useState(1),
    [size, setSize] = useState(10),
    [open, setOpen] = useState(false),
    [message, setMessage] = useState(false),
    [dates, setDates] = useState<[string, string]>(["", ""]);
  const [sort, setSort] = useState<"asc" | "desc" | null>(null);
  const select = (
    label: string,
    value: string,
    onChange: (v: string) => void,
    values: string[],
  ) => (
    <ChoiceSelect
      label={label}
      labelHidden={kind === "global-filter"}
      value={value}
      onChange={onChange}
      options={values.map((v) => ({ value: v, label: v }))}
    />
  );
  let content;
  if (kind === "global-filter")
    content = (
      <div className="flex flex-col gap-3">
        <FieldGroup className="flex-row flex-wrap items-center gap-2">
          {select("航季时段", season, setSeason, [
            "2026夏秋航季",
            "2025冬春航季",
          ])}
          <MultiSelect
            label="枢纽基地"
            labelHidden
            options={hubs}
            value={selected}
            onChange={setSelected}
          />
          <DateRangeFilter
            label="统计日期"
            labelHidden
            value={dates}
            onApply={(from, to) => setDates([from, to])}
          />
          <Button variant="outline" onClick={() => setMoreFilters(!moreFilters)} aria-expanded={moreFilters}>
            <SlidersHorizontal data-icon="inline-start" />
            更多筛选
          </Button>
        </FieldGroup>
        {moreFilters && <FieldGroup className="flex-row flex-wrap items-center gap-2">
          {select("机队机型", fleet, setFleet, [
            "全部机型",
            "宽体机",
            "窄体机",
          ])}
          {select("航线类型", route, setRoute, [
            "全部航线",
            "国内航线",
            "国际航线",
          ])}
          <Field className="w-40">
            <FieldLabel htmlFor="preview-query" className="sr-only">关键词</FieldLabel>
            <Input
              id="preview-query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索关键词"
            />
          </Field>
        </FieldGroup>}
        {moreFilters && (
        <RangeFilter
          label="统计范围"
          onApply={(from, to) =>
            setFilters(
              from && to
                ? [{ id: "range", label: `统计范围：${from} — ${to}` }]
                : [],
            )
          }
        />
        )}
        <ActiveFilters
          title="已生效条件与联动"
          items={[
            ...filters,
            ...selected.map((id) => ({
              id: `hub:${id}`,
              label: `基地：${hubs.find((h) => h.value === id)?.label || id}`,
            })),
            ...(dates[0]
              ? [{ id: "dates", label: `日期：${dates.join(" — ")}` }]
              : []),
          ]}
          onRemove={(id) =>
            id.startsWith("hub:")
              ? setSelected((current) =>
                  current.filter((v) => v !== id.slice(4)),
                )
              : id === "dates"
                ? setDates(["", ""])
                : setFilters((current) => current.filter((f) => f.id !== id))
          }
          onClear={() => {
            setFilters([]);
            setSelected([]);
            setDates(["", ""]);
            setQuery("");
          }}
        />
      </div>
    );
  else if (kind === "multiselect")
    content = (
      <MultiSelect
        label="枢纽基地"
        options={hubs}
        value={selected}
        onChange={setSelected}
      />
    );
  else if (kind === "date-range")
    content = (
      <DateRangeFilter
        label="统计日期"
        value={dates}
        onApply={(from, to) => setDates([from, to])}
      />
    );
  else if (kind === "inputs")
    content = (
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor={id}>关键词</FieldLabel>
          <Input
            id={id}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="输入关键词"
          />
        </Field>
        <Field data-disabled>
          <FieldLabel htmlFor={id + "-disabled"}>禁用状态</FieldLabel>
          <Input id={id + "-disabled"} disabled placeholder="不可编辑" />
        </Field>
      </FieldGroup>
    );
  else if (kind === "checkboxes")
    content = (
      <FieldSet>
        <FieldLegend>枢纽基地</FieldLegend>
        <FieldGroup>
          {hubs.map((h) => (
            <Field key={h.value} orientation="horizontal">
              <Checkbox
                id={id + h.value}
                checked={selected.includes(h.value)}
                onCheckedChange={(checked) =>
                  setSelected((current) =>
                    checked
                      ? [...current, h.value]
                      : current.filter((v) => v !== h.value),
                  )
                }
              />
              <FieldLabel htmlFor={id + h.value}>{h.label}</FieldLabel>
            </Field>
          ))}
        </FieldGroup>
      </FieldSet>
    );
  else if (kind === "alerts")
    content = (
      <Alert>
        <Info />
        <AlertTitle>筛选已更新</AlertTitle>
        <AlertDescription>图表与表格使用当前生效条件。</AlertDescription>
      </Alert>
    );
  else if (kind === "tags")
    content = (
      <ActiveFilters
        items={selected.map((value) => ({
          id: value,
          label: hubs.find((h) => h.value === value)!.label,
        }))}
        onRemove={(id) =>
          setSelected((current) => current.filter((v) => v !== id))
        }
        onClear={() => setSelected([])}
      />
    );
  else if (kind === "chart-toolbar")
    content = (
      <ChartToolbar
        grain={grain}
        onGrain={setGrain}
        showTable={table}
        onToggle={() => setTable(!table)}
        onInfo={() => setOpen(true)}
      />
    );
  else if (kind === "table-toolbar")
    content = (
      <TableToolbar
        query={query}
        onQuery={setQuery}
        onColumns={() => setOpen(true)}
      />
    );
  else if (kind === "columns")
    content = (
      <ColumnSettings
        columns={cols}
        visible={visible}
        onChange={setVisible}
        onReset={() => setVisible(cols.map((c) => c.value))}
      />
    );
  else if (kind === "pagination")
    content = (
      <Pagination
        page={page}
        pages={5}
        pageSize={size}
        onChange={(p, s) => {
          setPage(p);
          setSize(s);
        }}
      />
    );
  else if (kind === "sort")
    content = (
      <SortControl label="营业收入" direction={sort} onChange={setSort} />
    );
  else if (kind === "badge")
    content = (
      <div className="flex gap-3">
        <StatusBadge>正常</StatusBadge>
        <StatusBadge>观察</StatusBadge>
        <StatusBadge>预警</StatusBadge>
      </div>
    );
  else if (kind === "toast")
    content = (
      <>
        <Button variant="outline" onClick={() => setMessage(true)}>
          显示操作反馈
        </Button>
        {message && (
          <Toast kind="success" onClose={() => setMessage(false)}>
            操作已完成
          </Toast>
        )}
      </>
    );
  else if (kind === "empty")
    content = (
      <Empty>
        <EmptyHeader>
          <EmptyTitle>当前条件下没有数据</EmptyTitle>
        </EmptyHeader>
      </Empty>
    );
  else if (kind === "buttons")
    content = (
      <div className="flex flex-wrap gap-3">
        <Button>主要操作</Button>
        <Button variant="outline">次要操作</Button>
        <Button variant="ghost">文字操作</Button>
        <Button disabled>不可用</Button>
      </div>
    );
  else if (kind === "select")
    content = select("选择机型", fleet, setFleet, [
      "全部机型",
      "宽体机",
      "窄体机",
    ]);
  else if (kind === "tooltip")
    content = (
      <IconAction label="查看指标定义" onClick={() => setOpen(true)}>
        <MetricInfoIcon />
      </IconAction>
    );
  else
    content = (
      <Button variant="outline" onClick={() => setOpen(true)}>
        {kind === "explanation" ? "查看业务口径" : "打开对话框"}
      </Button>
    );
  return (
    <div className="bg-background p-4">
      {content}
      <ExplanationDialog
        open={open}
        onOpenChange={setOpen}
        title={
          kind === "table-toolbar"
            ? "自定义列配置"
            : kind === "explanation"
              ? "预算达成率"
              : "指标定义"
        }
      >
        {kind === "table-toolbar" ? (
          <ColumnSettings
            columns={cols}
            visible={visible}
            onChange={setVisible}
            onReset={() => setVisible(cols.map((c) => c.value))}
          />
        ) : (
          <p>当期实际收入 ÷ 预算目标 × 100%。此处为合成示例。</p>
        )}
      </ExplanationDialog>
    </div>
  );
}
export function TableGallery({
  variant = "tb02",
}: {
  variant?: "tb01" | "tb02";
}) {
  const [state, setState] = useState<TableState>({
    page: 1,
    pageSize: 10,
    keyword: "",
  });
  const doc = examples.document as unknown as Document,
    source = doc.computed!.components.details.rows as Config[];
  const columns = Object.entries(doc.manifest.datasets.sales.fields).map(
    ([key, f]: [string, any]) => ({
      key,
      title: f.label || key,
      align: f.type === "number" ? "right" : "left",
    }),
  );
  const rows = source.filter(
    (row) =>
      !state.keyword ||
      Object.values(row).some((v) =>
        String(v)
          .toLocaleLowerCase()
          .includes(state.keyword!.toLocaleLowerCase()),
      ),
  );
  const sorted = [...rows].sort((a, b) => {
    if (!state.sortCol) return 0;
    const av = a[state.sortCol],
      bv = b[state.sortCol],
      comparison =
        typeof av === "number" && typeof bv === "number"
          ? av - bv
          : String(av).localeCompare(String(bv), undefined, { numeric: true });
    return state.sortDir === "desc" ? -comparison : comparison;
  });
  const page = Math.min(
    state.page,
    Math.max(1, Math.ceil(sorted.length / state.pageSize)),
  );
  return (
    <Card className="h-[540px]">
      <CardHeader>
        <CardTitle>
          {variant === "tb01" ? "标准经营明细表" : "交互检索明细表"}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col">
      <DataTable
        config={{
          columns,
          rows: sorted.slice(
            (page - 1) * state.pageSize,
            page * state.pageSize,
          ),
        }}
        state={{ ...state, page, totalRows: sorted.length }}
        onChange={variant === "tb02" ? setState : undefined}
        onExport={() =>
          void browserDownload({
            name: "示例明细.csv",
            mimeType: "text/csv",
            blob: csvBlob(
              columns.map((c) => c.title),
              sorted.map((row) => columns.map((c) => row[c.key])),
            ),
          })
        }
      />
      </CardContent>
    </Card>
  );
}
