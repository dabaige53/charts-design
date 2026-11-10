import * as echarts from "echarts";
import type { Config, Document } from "./types";
export type ChartContext = {
    document: Document;
    id: string;
};
export declare const chartCodes: string[];
export declare const palette: {
    primary: string;
    primaryStrong: string;
    primarySoft: string;
    secondary: string;
    tertiary: string;
    slate: string;
    ink: string;
    inkMuted: string;
    inkSubtle: string;
    positive: string;
    negative: string;
    attention: string;
    canvas: string;
    surfaceGround: string;
    gridline: string;
    rule: string;
};
export declare function encodedOption(config: Config, context?: ChartContext): Config;
export declare function chartOption(config: Config, grain?: string, context?: ChartContext): Config;
export declare function chartData(config: Config, grain?: string, context?: ChartContext): {
    headers: string[];
    rows: any[][];
};
export declare function EChartSurface({ option, label, className, onReady, onSelect, }: {
    option: Config;
    label: string;
    className?: string;
    onReady?: (chart: echarts.ECharts | undefined) => void;
    onSelect?: (point: Config) => void;
}): import("react").JSX.Element;
