import { build } from "esbuild";
import postcss from "postcss";
import tailwindcss from "@tailwindcss/postcss";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import path from "node:path";
const root = fileURLToPath(new URL("..", import.meta.url));
// Inline the preset fonts so MCP documents and canvas previews need no font server.
const stylesheet = await build({
  entryPoints: [path.join(root, "src/styles.css")],
  bundle: true,
  write: false,
  conditions: ["style"],
  loader: { ".woff2": "dataurl", ".woff": "dataurl", ".ttf": "dataurl" },
});
const css = await postcss([tailwindcss()]).process(
  stylesheet.outputFiles[0].text,
  { from: path.join(root, "src/styles.css") },
);
const out = path.join(root, "dist");
await mkdir(out, { recursive: true });

// Claude Design supplies React 18. Keep a single React instance across x-import and the library.
const reactExports = [
  "Children",
  "Component",
  "Fragment",
  "Profiler",
  "PureComponent",
  "StrictMode",
  "Suspense",
  "cloneElement",
  "createContext",
  "createElement",
  "createFactory",
  "createRef",
  "forwardRef",
  "isValidElement",
  "lazy",
  "memo",
  "startTransition",
  "useCallback",
  "useContext",
  "useDebugValue",
  "useDeferredValue",
  "useEffect",
  "useId",
  "useImperativeHandle",
  "useInsertionEffect",
  "useLayoutEffect",
  "useMemo",
  "useReducer",
  "useRef",
  "useState",
  "useSyncExternalStore",
  "useTransition",
  "version",
];
const globalsPlugin = {
  name: "design-react-globals",
  setup(builder) {
    builder.onResolve(
      { filter: /^react(?:\/jsx-runtime)?$|^react-dom(?:\/client)?$/ },
      (args) => ({ path: args.path, namespace: "design-globals" }),
    );
    builder.onLoad({ filter: /.*/, namespace: "design-globals" }, (args) => {
      if (args.path === "react/jsx-runtime")
        return {
          contents:
            "const R=window.React;export const Fragment=R.Fragment;export function jsx(type,props,key){return R.createElement(type,key===undefined?props:{...props,key});}export const jsxs=jsx;",
          loader: "js",
        };
      const react = args.path === "react",
        ns = react ? "React" : "ReactDOM";
      const names = react
        ? reactExports
        : [
            "createPortal",
            "flushSync",
            "findDOMNode",
            "render",
            "hydrate",
            "unmountComponentAtNode",
            "unstable_batchedUpdates",
            "createRoot",
            "hydrateRoot",
            "version",
          ];
      return {
        contents: `const R=window.${ns};export default R;${names.map((name) => `export const ${name}=R.${name};`).join("")}`,
        loader: "js",
      };
    });
  },
};
const gallery = await build({
  entryPoints: [path.join(root, "src/design.tsx")],
  bundle: true,
  write: false,
  format: "iife",
  globalName: "McKinseyMDS",
  plugins: [globalsPlugin],
  target: "es2022",
  minify: true,
  legalComments: "inline",
  define: { "process.env.NODE_ENV": '"production"' },
});
const header =
  "/* @ds-bundle: " +
  JSON.stringify({
    format: 4,
    namespace: "McKinseyMDS",
    components: [
      "ChartTile",
      "MetricTile",
      "TableGallery",
      "ControlPreview",
      "MultiSelect",
      "ActiveFilters",
      "RangeFilter",
      "ChartToolbar",
      "TableToolbar",
      "ColumnSettings",
      "Pagination",
      "SortControl",
      "StatusBadge",
      "Toast",
      "ExplanationDialog",
      "Button",
      "Card",
    ].map((name) => ({ name })),
  }) +
  " */\n";
await writeFile(
  path.join(out, "bundle.js"),
  header + gallery.outputFiles[0].text.replaceAll("<!--", "\\x3C!--"),
);
// The design editor loads registered font files from tokens.json.
await writeFile(
  path.join(out, "bundle.css"),
  css.css.replace(/@font-face\s*\{[^}]*\}/g, ""),
);
await build({
  entryPoints: [path.join(root, "src/index.ts")],
  outfile: path.join(out, "components.js"),
  bundle: true,
  format: "esm",
  external: ["react", "react-dom", "react-dom/client", "react/jsx-runtime"],
  target: "es2022",
  minify: true,
});
const app = await build({
  entryPoints: [path.join(root, "src/main.tsx")],
  metafile: true,
  bundle: true,
  write: false,
  format: "iife",
  target: "es2022",
  minify: true,
  legalComments: "inline",
  define: { "process.env.NODE_ENV": '"production"' },
});
const previewInputs = Object.keys(app.metafile.inputs).filter((file) =>
  /(?:^|\/)(?:fixtures|docs)\//.test(file),
);
if (previewInputs.length)
  throw Error("应用构建引用了设计预览或文档：" + previewInputs.join(", "));
await writeFile(
  path.join(out, "app.inputs.json"),
  JSON.stringify(Object.keys(app.metafile.inputs), null, 2) + "\n",
);
const js = app.outputFiles[0].text;
await writeFile(path.join(out, "app.js"), js);
const staticApp = await build({
  entryPoints: [path.join(root, "src/static-main.tsx")],
  bundle: true,
  write: false,
  format: "iife",
  target: "es2022",
  minify: true,
  legalComments: "inline",
  define: { "process.env.NODE_ENV": '"production"' },
});
const staticJs = staticApp.outputFiles[0].text;
await writeFile(path.join(out, "static-app.js"), staticJs);
await writeFile(path.join(out, "app.css"), css.css);
await build({
  entryPoints: [path.join(root, "../dashboard_runtime/web/static-worker.mjs")],
  outfile: path.join(out, "static-worker.js"),
  bundle: true,
  format: "esm",
  target: "es2022",
  minify: true,
});
const worker = await readFile(path.join(out, "static-worker.js"));
const id = createHash("sha256")
  .update(js)
  .update(css.css)
  .update(worker)
  .update(staticJs)
  .digest("hex")
  .slice(0, 16);
await writeFile(
  path.join(out, "build.json"),
  JSON.stringify({
    id,
    format: 1,
    entries: ["app.js", "app.css", "static-worker.js", "static-app.js"],
    components: 40,
    metrics: 16,
  }) + "\n",
);
console.log(
  JSON.stringify({
    output: out,
    id,
    appBytes: Buffer.byteLength(js) + Buffer.byteLength(css.css),
    staticAppBytes: Buffer.byteLength(staticJs),
    designBytes: gallery.outputFiles[0].contents.length,
  }),
);
