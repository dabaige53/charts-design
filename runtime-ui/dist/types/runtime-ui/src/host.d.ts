import type { Config } from "./types";
export type Download = (file: {
    name: string;
    mimeType: string;
    blob: Blob;
}) => Promise<void>;
export declare function browserDownload({ name, blob, }: {
    name: string;
    mimeType: string;
    blob: Blob;
}): Promise<void>;
export declare function csvBlob(headers: string[], rows: any[][]): Blob;
export declare function deliverExport(value: Config, download: Download, read?: (offset: number, limit: number) => Promise<Config>): Promise<void>;
