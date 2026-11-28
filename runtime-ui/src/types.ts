export type Config = Record<string, any>;
export type AnnotationAccess = {
  endpoint: string;
  canRead: boolean;
  canAnnotate: boolean;
  canManageAnnotations: boolean;
  scope: string;
  author?: { name: string; verified: boolean };
};
declare global {
  interface Window {
    __chartsBoot: Config;
    __chartsInitialPreview?: Promise<Config | null>;
    __chartsReady: () => Promise<void>;
  }
}
export type Position = {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
};
export type Filter = {
  id: string;
  label: string;
  field: string;
  op: "in" | "range" | "contains";
  selectionMode?: "single" | "multiple";
  alwaysVisible?: boolean;
  required?: boolean;
  scope?: "report" | "table";
  values: any[];
  componentIds: string[];
};
export type ComponentSpec = {
  kind: string;
  family?: string;
  title: string;
  subtitle?: string;
  config?: Config;
  presentation?: Config;
  [key: string]: any;
};
export type Document = {
  annotationAccess?: AnnotationAccess;
  publication?: { shareId: string; revision: number };
  staticPages?: { id: string; title: string; path: string }[];
  id: string;
  revision: number;
  dataVersion?: string;
  manifest: {
    title: string;
    meta?: Record<string, string>;
    components: Record<string, ComponentSpec>;
    filters: Filter[];
    annotations?: Config[];
    layout: Record<string, Position[]>;
    metrics: Config;
    datasets: Config;
    sources?: Config;
    viewMode?: string;
    report?: Config;
  };
  snapshot: { datasets: Config; [key: string]: any };
  computed?: {
    components: Record<string, Config>;
    tables: Config;
    grouped?: Config;
    filterOptions?: Record<string, any[]>;
    filterPages?: Config;
  };
  [key: string]: any;
};
export type ToolCall = (name: string, args?: Config) => Promise<Config>;
export type TableState = {
  page: number;
  pageSize: number;
  keyword?: string;
  sortCol?: string;
  sortDir?: "asc" | "desc";
  columns?: string[];
  visible?: string[];
};
export function hasLiveData(document: Document): boolean {
  return Object.values(document.manifest.datasets).some((dataset) => dataset.mode === "live");
}
