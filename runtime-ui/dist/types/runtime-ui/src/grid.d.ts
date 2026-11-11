import React from "react";
import type { Document, Position } from "./types";
export declare function DashboardGrid({ document: doc, editing, onLayoutChange, children, }: {
    document: Document;
    editing: boolean;
    onLayoutChange: (p: Position[], bp: string) => void;
    children: (id: string) => React.ReactNode;
}): React.JSX.Element;
