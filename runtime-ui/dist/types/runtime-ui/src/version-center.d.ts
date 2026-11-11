import React from "react";
import type { Document, ToolCall } from "./types";
export declare function VersionCenter({ open, onOpenChange, document, call, onRestore, onSaved }: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    document: Document;
    call: ToolCall;
    onRestore: (revision: number) => Promise<void>;
    onSaved: () => Promise<void>;
}): React.JSX.Element;
