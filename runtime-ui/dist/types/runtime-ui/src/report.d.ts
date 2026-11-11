import type React from "react";
import type { Document } from "./types";
export declare function ReportView({ document: doc, component, }: {
    document: Document;
    component: (id: string) => React.ReactNode;
}): React.JSX.Element;
