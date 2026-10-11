# Original-component fidelity

The first runtime incorrectly reduced c01/c02 to native bars and original KPI cards to text. This change removes those lossy conversions. The original executive-charts source is the component authority, not a visual reference to imitate.

## Architecture

`runtime-ui/extract-original.py` imports the original dashboard template, scoped runtime, chart builders, explanation renderer and catalog at build time. `build.mjs` compiles their original utility CSS, sanitizes HTML sinks through a typed AST transform, and bundles the renderer. Each component mounts into a ShadowRoot: no duplicate iframe card, no CDN dependency in normal previews or HTML exports. Generated source hashes are recorded in `runtime-ui/generated/provenance.json`.

The existing versioned service, MCP tools, CLI, query provenance and GridStack layouts remain. SQL/semantic inspection is an additional action, not a replacement for the original business-definition dialog.

## Preservation contract

- Workspace import keeps every original chart config, presentation, KPI type and fields, and table columns/rows. No chart-type substitution and no KPI-to-text conversion.
- All 40 original chart builders and 9 KPI renderer branches are bundled from source. Examples are preview fixtures only; real components still require explicit business data.
- Original chart card shell, geometry, units, tooltip/legend configuration, applicable granularity buttons, chart/table toggle, CSV, 2x PNG, fullscreen and rich explanation content are retained.
- Original table sorting, columns drawer, column visibility/reordering, restore defaults, pagination and copy/export controls are retained. Native runtime tables also use that renderer.
- Original aggregate snapshots do not become live cross-filtered datasets merely because they were imported. Original filter definitions are preserved as metadata until their data bindings are deliberately configured.
- Native chart-type switching stays compatibility-checked. Arbitrary conversion between all original chart codes is not implemented.

## Verification

`tests/runtime/test_fidelity.py` checks lossless migration and uses real Chromium for original toolbar, mini-trend KPI, period persistence, chart/table toggle, explanation dialog, column visibility/restore, offline bundling and mobile overflow. This is a representative integration test, not a pixel-perfect audit of all 40 charts, all 9 KPI variants or all browsers.

Rebuild after checkout:

```sh
npm --prefix runtime-ui install
npm --prefix runtime-ui run build
python3 -m pytest tests/runtime -q
```

Original unbound components remain explicit snapshots; native governed metrics retain shared filter and query provenance behavior. Existing dashboards already imported by the first version must be reimported from their original workspace to recover discarded presentation fields. The runtime cannot reconstruct fields that were deleted from a previously saved artifact.
