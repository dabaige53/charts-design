import React from "react";
import { type Download } from "./host";
import type { Document, ToolCall } from "./types";
export declare function DashboardApp({ initial, call, onFullscreen, download, readOnly, staticMode, buildId, primaryFilterIds, projectRoot, }: {
    initial: Document;
    call: ToolCall;
    onFullscreen?: () => void;
    download?: Download;
    readOnly?: boolean;
    staticMode?: boolean;
    buildId?: string;
    primaryFilterIds?: string[];
    projectRoot?: string | null;
}): React.JSX.Element;
