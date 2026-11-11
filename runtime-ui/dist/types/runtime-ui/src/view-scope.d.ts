import type { Document, Filter } from "./types";
export declare function filterScope(document: Document, filters: Filter[], componentId?: string): {
    id: string;
    label: string;
    value: string;
}[];
export declare function ViewScope({ document, filters, grains, }: {
    document: Document;
    filters: Filter[];
    grains: Record<string, string>;
}): import("react").JSX.Element | null;
