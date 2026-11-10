// Explicit design snapshot; the build itself writes only runtime-ui/dist.
import { mkdir, copyFile, readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
const root = fileURLToPath(new URL("..", import.meta.url));
const destination = path.resolve(
  root,
  "../docs/design-system/project/components",
);
await mkdir(destination, { recursive: true });
const script = await readFile(path.join(root, "dist/bundle.js"), "utf8");
const names = [
  "Buttons",
  "Cards",
  "Select",
  "MultiSelect",
  "DatePicker",
  "Checkboxes",
  "TextInputs",
  "Tags",
  "Badges",
  "Tooltips",
  "Modals",
  "DataTables",
  "Pagination",
  "Alerts",
  "ChartTile",
  "MetricTile",
];
const header =
  "/* @ds-bundle: " +
  JSON.stringify({
    format: 4,
    namespace: "McKinseyMDS",
    components: names.map((name) => ({ name })),
  }) +
  " */";
await writeFile(
  path.join(destination, "bundle.js"),
  header + script.slice(script.indexOf("\n")),
);
const fonts = path.resolve(destination, "../fonts");
await mkdir(fonts, { recursive: true });
const fontFaces = [];
for (const family of ["inter", "lora"]) {
  for (const style of ["normal", "italic"]) {
    const name = `${family}-latin-wght-${style}.woff2`;
    await copyFile(
      path.join(root, `node_modules/@fontsource-variable/${family}/files`, name),
      path.join(fonts, name),
    );
    const display = family === "inter" ? "Inter Variable" : "Lora Variable";
    const weight = family === "inter" ? "100 900" : "400 700";
    fontFaces.push(
      `@font-face{font-family:"${display}";font-style:${style};font-weight:${weight};font-display:swap;src:url("../fonts/${name}") format("woff2");}`,
    );
  }
}
await writeFile(
  path.join(destination, "bundle.css"),
  fontFaces.join("\n") + "\n" + await readFile(path.join(root, "dist/bundle.css"), "utf8"),
);
console.log(
  JSON.stringify({ destination, files: ["bundle.js", "bundle.css"], fonts }),
);
