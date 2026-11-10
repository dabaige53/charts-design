import type { Config, Document, Filter, Position, TableState, ToolCall } from "./types";
type View = {
    filters: Filter[];
    tables: Record<string, TableState>;
    grains: Record<string, string>;
    linkageSource?: string;
};
export declare function mergeView(document: Document, patch: Config): Document;
export declare function useDashboardRuntime(initial: Document, call: ToolCall): {
    document: Document;
    view: View;
    loading: string[];
    error: string;
    errors: Record<string, string>;
    saving: boolean;
    activate: (id: string) => void;
    setFilter: (id: string, values: any[]) => void;
    setTable: (id: string, state: TableState) => void;
    setGrain: (id: string, grain: string) => void;
    clear: () => void;
    link: (filter: Filter, sourceId: string) => void;
    reload: () => Promise<void>;
    save: (operations: Config[]) => Promise<boolean>;
    restore: (revision: number) => Promise<void>;
    accept: (doc: Document, preserveView?: boolean) => void;
    setError: import("react").Dispatch<import("react").SetStateAction<string>>;
    setAnnotations: (annotations: Config[]) => void;
    loaded: import("react").RefObject<Set<string>>;
    retry: (id: string) => Promise<void>;
};
export declare function layoutOperations(title: string, layouts: Record<string, Position[]>): ({
    op: string;
    breakpoint: string;
    value: Position[];
} | {
    op: string;
    value: string;
})[];
export {};
