import { mountApp } from "./app-root";
import { StaticSite } from "./static";

// Shares use the shared dashboard UI without loading the MCP host adapter.
mountApp(<StaticSite />);
