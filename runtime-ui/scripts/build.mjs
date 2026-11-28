import { build } from "esbuild";
import postcss from "postcss";
import tailwindcss from "@tailwindcss/postcss";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createHash } from "node:crypto";
import { brotliCompressSync, constants, gzipSync } from "node:zlib";
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
const appOptions = {
  entryPoints: [path.join(root, "src/main.tsx")],
  metafile: true,
  bundle: true,
  write: false,
  format: "iife",
  target: "es2022",
  minify: true,
  legalComments: "inline",
  define: { "process.env.NODE_ENV": '"production"', WEB_BUILD: "false" },
};
const app = await build(appOptions);
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
await writeFile(path.join(out, "app.css"), css.css);
await build({
  entryPoints: [path.join(root, "../runtime-ui/shared/static-worker.mjs")],
  outfile: path.join(out, "static-worker.js"),
  bundle: true,
  format: "esm",
  target: "es2022",
  minify: true,
});
const worker = await readFile(path.join(out, "static-worker.js"));
const web = await build({ ...appOptions, define: { ...appOptions.define, WEB_BUILD: "true" } });
const webJs = web.outputFiles[0].contents;
const fonts = new Map();
const webCss = css.css.replace(/data:font\/(woff2?|ttf);base64,([A-Za-z0-9+/=]+)/g, (_, extension, data) => {
  const bytes = Buffer.from(data, "base64");
  const digest = createHash("sha256").update(bytes).digest("hex").slice(0, 16);
  const name = `fonts/${digest}.${extension}`;
  fonts.set(name, bytes);
  return name;
});
const webEntries = new Map([["app.js", webJs], ["app.css", webCss], ["static-worker.js", worker]]);
const webId = createHash("sha256").update(webJs).update(webCss).update(worker).digest("hex").slice(0, 16);
await mkdir(path.join(out, "web/fonts"), { recursive: true });
await Promise.all([...webEntries, ...fonts].map(([name, bytes]) => writeFile(path.join(out, "web", name), bytes)));
for (const [name, bytes] of webEntries) {
  const file = path.join(out, "web", name);
  const input = typeof bytes === "string" ? Buffer.from(bytes) : bytes;
  await Promise.all([
    writeFile(file + ".br", brotliCompressSync(input, { params: { [constants.BROTLI_PARAM_QUALITY]: 9 } })),
    writeFile(file + ".gz", gzipSync(input, { level: 9 })),
  ]);
}
const id = createHash("sha256")
  .update(js)
  .update(css.css)
  .update(worker)
  .digest("hex")
  .slice(0, 16);
await writeFile(
  path.join(out, "build.json"),
  JSON.stringify({
    id,
    webId,
    fonts: [...fonts.keys()],
    format: 1,
    entries: ["app.js", "app.css", "static-worker.js"],
    staticDataFormats: ["json-gzip", "parquet-v1"],
    components: 40,
    metrics: 16,
  }) + "\n",
);
console.log(
  JSON.stringify({
    output: out,
    id,
    appBytes: Buffer.byteLength(js) + Buffer.byteLength(css.css),
    designBytes: gallery.outputFiles[0].contents.length,
  }),
);
