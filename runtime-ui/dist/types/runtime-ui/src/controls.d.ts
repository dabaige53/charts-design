import { type ReactNode } from "react";
export type Choice = {
    value: string;
    label: string;
};
export type ActiveFilter = {
    id: string;
    label: string;
};
export type ChoicePage = {
    options: Choice[];
    hasMore: boolean;
    total?: number;
};
export type ChoiceLoader = (search: string, offset: number) => Promise<ChoicePage>;
export declare function ChoiceSelect({ label, value, options, onChange, disabled, labelHidden, }: {
    label: string;
    value: string;
    options: Choice[];
    onChange: (value: string) => void;
    disabled?: boolean;
    labelHidden?: boolean;
}): import("react").JSX.Element;
export declare function MultiSelect({ label, options, value, onChange, loadOptions, disabled, labelHidden, single, }: {
    label: string;
    options: Choice[];
    value: string[];
    onChange: (value: string[]) => void;
    loadOptions?: ChoiceLoader;
    disabled?: boolean;
    labelHidden?: boolean;
    single?: boolean;
}): import("react").JSX.Element;
export declare function ActiveFilters({ items, onRemove, onClear, title, showClear, }: {
    items: ActiveFilter[];
    onRemove: (id: string) => void;
    onClear: () => void;
    title?: string;
    showClear?: boolean;
}): import("react").JSX.Element;
export declare function RangeFilter({ label, onApply, value, type, }: {
    label: string;
    onApply: (from: string, to: string) => void;
    value?: [string, string];
    type?: "number" | "text";
}): import("react").JSX.Element;
export declare function DateRangeFilter({ label, value, onApply, labelHidden, }: {
    label: string;
    value?: [string, string];
    onApply: (from: string, to: string) => void;
    labelHidden?: boolean;
}): import("react").JSX.Element;
export declare function IconAction({ label, onClick, disabled, children, unavailable, size, variant, pressed, }: {
    label: string;
    onClick?: () => void;
    disabled?: boolean;
    children: ReactNode;
    unavailable?: string;
    size?: "icon-xs" | "icon-sm";
    variant?: "ghost" | "outline" | "default";
    pressed?: boolean;
}): import("react").JSX.Element;
export declare function ChartToolbar({ chartType, onChartType, grain, onGrain, showTable, onToggle, onExport, onCopy, onImage, onExpand, expanded, onInfo, }: {
    chartType?: string;
    onChartType?: (value: string) => void;
    grain?: string;
    onGrain?: (v: string) => void;
    showTable: boolean;
    onToggle?: () => void;
    onExport?: () => void;
    onCopy?: () => void;
    onImage?: () => void;
    onExpand?: () => void;
    expanded?: boolean;
    onInfo?: () => void;
}): import("react").JSX.Element;
export declare function TableToolbar({ query, onQuery, onColumns, onExport, }: {
    query: string;
    onQuery: (v: string) => void;
    onColumns: () => void;
    onExport?: () => void;
}): import("react").JSX.Element;
export declare function ColumnSettings({ columns, visible, onChange, onReset, order, onOrderChange, }: {
    columns: Choice[];
    visible: string[];
    onChange: (ids: string[]) => void;
    onReset: () => void;
    order?: string[];
    onOrderChange?: (ids: string[]) => void;
}): import("react").JSX.Element;
export declare function Pagination({ page, pages, pageSize, onChange, }: {
    page: number;
    pages: number;
    pageSize: number;
    onChange: (page: number, size: number) => void;
}): import("react").JSX.Element;
export declare function SortControl({ label, direction, onChange, align, }: {
    label: string;
    direction: "asc" | "desc" | null;
    onChange: (direction: "asc" | "desc") => void;
    align?: "left" | "center" | "right";
}): import("react").JSX.Element;
export declare function StatusBadge({ children }: {
    children: ReactNode;
}): import("react").JSX.Element;
export declare function Toast({ kind, children, onClose, }: {
    kind: "success" | "info" | "warning";
    children: ReactNode;
    onClose: () => void;
}): import("react").JSX.Element;
export declare function ExplanationDialog({ open, onOpenChange, title, children, }: {
    open: boolean;
    onOpenChange: (value: boolean) => void;
    title: string;
    children: ReactNode;
}): import("react").JSX.Element;
