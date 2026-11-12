export type Config = Record<string, any>;
declare global {
  interface Window {
    __chartsBoot: Config;
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
