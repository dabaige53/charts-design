import type { Config, TableState } from "./types";
export declare function DataTable({ config, state, onChange, onExport, onSaveState, loading, error, toolbarTarget, }: {
    config: Config;
    state: TableState & {
        totalRows?: number;
    };
    onChange?: (next: TableState) => void;
    onExport?: () => void;
    onSaveState?: () => void;
    loading?: boolean;
    error?: string;
    toolbarTarget?: HTMLElement | null;
}): import("react").JSX.Element;
