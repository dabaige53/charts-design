# Original-component fidelity

The first runtime incorrectly reduced c01/c02 to native bars and original KPI cards to text. This change removes those lossy conversions. The original executive-charts source is the component authority, not a visual reference to imitate.

> **Current Status Notice (2026-11-10 Architecture Rebuild)**
> The historical extraction script (`runtime-ui/extract-original.py`) and legacy bundle build (`runtime-ui/build.mjs`) have been removed for the unified React + TypeScript / Tailwind CSS v4 / shadcn/ui / ECharts / GridStack / Lucide rebuild.
> This document is retained as a specification for lossless component fidelity: ensuring that all 40 chart contracts, 16 KPI card definitions, units, presentation metadata, and table configurations survive migrations without structural loss.

## Architecture

In the historical architecture, `runtime-ui/extract-original.py` and `build.mjs` extracted components into a ShadowRoot runtime bundle. In the ongoing rebuild, the presentation layer is being re-implemented directly as a native React + TypeScript component library, while the underlying component schemas, presentation contracts, and data-binding models described below remain authoritative.

The existing versioned service, MCP tools, CLI, query provenance and GridStack layouts remain. SQL/semantic inspection is an additional action, not a replacement for the original business-definition dialog.

## Preservation contract

- Workspace import keeps every original chart config, presentation, KPI type and fields, and table columns/rows. No chart-type substitution and no KPI-to-text conversion.
- All 40 original chart builders and 16 KPI renderer branches (mc01–mc09 original, mc10–mc16 added to the same engine) are bundled from source. Examples are preview fixtures only; real components still require explicit business data.
- Original chart card shell, geometry, units, tooltip/legend configuration, applicable granularity buttons, chart/table toggle, CSV, 2x PNG, fullscreen and rich explanation content are retained.
- Original table sorting, columns drawer, column visibility/reordering, restore defaults, pagination and copy/export controls are retained. Native runtime tables also use that renderer.
- Original aggregate snapshots do not become live cross-filtered datasets merely because they were imported. Original filter definitions are preserved as metadata until their data bindings are deliberately configured.
- Native chart-type switching stays compatibility-checked. Arbitrary conversion between all original chart codes is not implemented.

## Verification and migration contract

Original unbound components remain explicit snapshots; native governed metrics retain shared filter and query provenance behavior. Existing dashboards already imported by the first version must be reimported from their original workspace to recover discarded presentation fields. The runtime cannot reconstruct fields that were deleted from a previously saved artifact.
