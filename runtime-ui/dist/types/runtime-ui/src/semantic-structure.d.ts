import type { Config } from "./types";
type Annotation = {
    id: string;
    anchor: [number, number];
    label: [number, number];
    align?: "left" | "center" | "right";
    metricId?: string;
    name?: string;
    description?: string;
};
type StructureDiagram = {
    version: 1;
    viewBox: [number, number, number, number];
    svg: string;
    annotations: Annotation[];
    status?: "ready" | "stale";
};
/** Saved geometry, never reconstructed from chart type or filtered values. */
export declare function SemanticStructure({ diagram, metrics, compact }: {
    diagram?: StructureDiagram;
    metrics: Config;
    compact?: boolean;
}): import("react").JSX.Element;
export {};
