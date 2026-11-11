import type { Config } from "../types";
export type ChartDefinition = {
  code: string;
  hasGranularity?: boolean;
  defaultGranularity?: string;
  optionBuilder: (
    data: Config,
    grain: string,
    tokens: Config,
    config: Config,
  ) => Config;
  tableDataExtractor: (
    data: Config,
    grain: string,
    config: Config,
  ) => { headers: string[]; rows: any[][] };
};
