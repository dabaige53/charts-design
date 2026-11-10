import type { Config, Document } from "./types";
export declare function historicalData(doc: Document, id: string): {
    headers: any[];
    rows: any[][];
};
export declare function historicalOption(doc: Document, id: string, palette: Config): Config;
