import React from "react";
import { type Download } from "./host";
import type { Document, ToolCall } from "./types";
export declare function DashboardApp({ initial, call, onFullscreen, pageFullscreen, download, readOnly, staticMode, buildId, primaryFilterIds, projectRoot, }: {
    initial: Document;
    call: ToolCall;
    onFullscreen?: () => void;
    pageFullscreen?: boolean;
    download?: Download;
    readOnly?: boolean;
    staticMode?: boolean;
    buildId?: string;
    primaryFilterIds?: string[];
    projectRoot?: string | null;
}): React.JSX.Element;
