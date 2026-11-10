import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./components/ui/table";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "./components/ui/sheet";
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerDescription,
} from "./components/ui/drawer";
import { Button } from "./ui";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
} from "./components/ui/empty";
import { Skeleton } from "./components/ui/skeleton";
import { Alert, AlertDescription } from "./components/ui/alert";
import {
  ColumnSettings,
  Pagination,
  SortControl,
  TableToolbar,
} from "./controls";
import { cn } from "./ui";
import type { Config, TableState } from "./types";

// Rows are already searched, sorted and paged by the runtime (or the design adapter).
export function DataTable({
  config,
  state,
  onChange,
  onExport,
  onSaveState,
  loading = false,
  error,
  toolbarTarget,
}: {
  config: Config;
  state: TableState & { totalRows?: number };
  onChange?: (next: TableState) => void;
  onExport?: () => void;
  onSaveState?: () => void;
  loading?: boolean;
  error?: string;
  toolbarTarget?: HTMLElement | null;
}) {
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [mobile, setMobile] = useState(
    () => window.matchMedia("(max-width:600px)").matches,
  );
  useEffect(() => {
    const query = window.matchMedia("(max-width:600px)"),
      update = () => setMobile(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  const specs: Config[] = config.columns || [],
    rows: Config[] = config.rows || [];
  const total = state.totalRows ?? rows.length,
    pages = Math.max(1, Math.ceil(total / state.pageSize));
  const all = specs.map((c) => String(c.key)),
    order = state.columns ?? all,
    visible = state.visible ?? all;
  const columns = useMemo<ColumnDef<Config>[]>(
    () =>
      specs.map((c) => ({
        id: String(c.key),
        accessorFn: (row) => row[c.key],
        header: () =>
          onChange ? (
            <SortControl
              label={c.title || c.label || c.key}
              direction={
                state.sortCol === c.key ? state.sortDir || "asc" : null
              }
              onChange={(direction) =>
                onChange({
                  ...state,
                  page: 1,
                  sortCol: c.key,
                  sortDir: direction,
                })
              }
            />
          ) : (
            c.title || c.label || c.key
          ),
        cell: (info) =>
          info.getValue() == null ? "—" : String(info.getValue()),
        meta: { align: c.align },
      })),
    [specs, onChange, state],
  );
  const sorting: SortingState = state.sortCol
    ? [{ id: state.sortCol, desc: state.sortDir === "desc" }]
    : [];
  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    rowCount: total,
    state: {
      pagination: { pageIndex: state.page - 1, pageSize: state.pageSize },
      sorting,
      columnOrder: order,
      columnVisibility: Object.fromEntries(
        all.map((id) => [id, visible.includes(id)]),
      ),
    },
  });
  const settings = onChange ? (
    <>
      <ColumnSettings
        columns={specs.map((c) => ({
          value: String(c.key),
          label: c.title || c.label || c.key,
        }))}
        visible={visible}
        order={order}
        onChange={(ids) => onChange({ ...state, visible: ids })}
        onOrderChange={(ids) => onChange({ ...state, columns: ids })}
        onReset={() => onChange({ ...state, visible: all, columns: all })}
      />
      {onSaveState && (
        <div className="p-4">
          <Button onClick={onSaveState}>保存列配置</Button>
        </div>
      )}
    </>
  ) : null;
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2" aria-busy={loading}>
      {onChange && (toolbarTarget ? createPortal(
        <div className="screen-only">
          <TableToolbar
            query={state.keyword || ""}
            onQuery={(keyword) => onChange({ ...state, page: 1, keyword })}
            onColumns={() => setColumnsOpen(true)}
            onExport={visible.length ? onExport : undefined}
          />
        </div>, toolbarTarget,
      ) : !toolbarTarget && (
        <div className="screen-only">
          <TableToolbar
            query={state.keyword || ""}
            onQuery={(keyword) => onChange({ ...state, page: 1, keyword })}
            onColumns={() => setColumnsOpen(true)}
            onExport={visible.length ? onExport : undefined}
          />
        </div>
      ))}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <div className="min-h-0 flex-1 overflow-auto">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((group) => (
              <TableRow key={group.id}>
                {group.headers.map((header) => (
                  <TableHead
                    key={header.id}
                    scope="col"
                    aria-sort={
                      state.sortCol === header.id
                        ? state.sortDir === "desc"
                          ? "descending"
                          : "ascending"
                        : "none"
                    }
                    className={cn(
                      (header.column.columnDef.meta as { align?: string })
                        ?.align === "right" && "text-right",
                    )}
                  >
                    {flexRender(
                      header.column.columnDef.header,
                      header.getContext(),
                    )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {loading && !rows.length ? (
              <TableRow>
                <TableCell colSpan={Math.max(1, visible.length)}>
                  <Skeleton className="h-24 w-full" />
                </TableCell>
              </TableRow>
            ) : table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell
                      key={cell.id}
                      className={cn(
                        (cell.column.columnDef.meta as { align?: string })
                          ?.align === "right" && "text-right",
                      )}
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={Math.max(1, visible.length)}>
                  <Empty>
                    <EmptyHeader>
                      <EmptyTitle>
                        {visible.length ? "没有匹配数据" : "未显示任何列"}
                      </EmptyTitle>
                      <EmptyDescription>
                        {visible.length
                          ? "调整筛选条件或搜索词后重试。"
                          : "打开自定义列配置，勾选需要显示的列。"}
                      </EmptyDescription>
                    </EmptyHeader>
                  </Empty>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <footer className="screen-only flex flex-wrap items-end justify-between gap-2">
        <span className="text-xs text-muted-foreground">
          共 {total.toLocaleString()} 行
        </span>
        {onChange && (
          <Pagination
            page={state.page}
            pages={pages}
            pageSize={state.pageSize}
            onChange={(page, pageSize) =>
              onChange({ ...state, page, pageSize })
            }
          />
        )}
      </footer>
      {onChange &&
        (mobile ? (
          <Drawer open={columnsOpen} onOpenChange={setColumnsOpen}>
            <DrawerContent>
              <DrawerHeader>
                <DrawerTitle>自定义列配置</DrawerTitle>
                <DrawerDescription>
                  调整当前表格的显示列与顺序。
                </DrawerDescription>
              </DrawerHeader>
              <div className="overflow-y-auto">{settings}</div>
            </DrawerContent>
          </Drawer>
        ) : (
          <Sheet open={columnsOpen} onOpenChange={setColumnsOpen}>
            <SheetContent className="overflow-y-auto">
              <SheetHeader>
                <SheetTitle>自定义列配置</SheetTitle>
                <SheetDescription>
                  调整当前表格的显示列与顺序。
                </SheetDescription>
              </SheetHeader>
              {settings}
            </SheetContent>
          </Sheet>
        ))}
    </div>
  );
}
