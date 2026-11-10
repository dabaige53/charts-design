import type { Config, Document, Filter } from "./types";
export declare function SemanticDetails({ value, component, document, componentId, filters, }: {
    value: Config | null;
    component: Config;
    document: Document;
    componentId: string;
    filters: Filter[];
}): import("react").JSX.Element | null;
