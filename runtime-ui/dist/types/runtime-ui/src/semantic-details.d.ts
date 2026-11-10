import type { Config, Document, Filter, TableState } from "./types";
export declare function SemanticDetails({ value, component, document, componentId, filters, onReadData, }: {
    value: Config | null;
    component: Config;
    document: Document;
    componentId: string;
    filters: Filter[];
    onReadData?: (state: TableState) => Promise<Config>;
}): import("react").JSX.Element | null;
