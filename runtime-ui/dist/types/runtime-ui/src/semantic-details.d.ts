import type { Config, Document, Filter, TableState } from "./types";
export declare function SemanticDetails({ value, component, document, componentId, filters, onReadData, grain, }: {
    value: Config | null;
    component: Config;
    document: Document;
    componentId: string;
    filters: Filter[];
    onReadData?: (state: TableState) => Promise<Config>;
    grain?: string;
}): import("react").JSX.Element | null;
