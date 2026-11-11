import { type RefObject } from "react";
import type { Config, Document, Filter, ToolCall } from "./types";
export declare function PositionComments({ document: doc, root, active, onActiveChange, onActivityChange, call, readOnly, filters, projectRoot, onNotesChange, }: {
    document: Document;
    root: RefObject<HTMLDivElement | null>;
    active: boolean;
    onActiveChange: (value: boolean) => void;
    onActivityChange: (value: boolean) => void;
    call: ToolCall;
    readOnly: boolean;
    filters: Filter[];
    projectRoot?: string | null;
    onNotesChange: (notes: Config[]) => void;
}): import("react").ReactPortal | null;
