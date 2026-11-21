import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
if (args.length !== 2) {
  console.error("Usage: bun deploy/pages/build.mjs <backend-web-dist> <output-directory>");
  process.exit(1);
}
const source = resolve(args[0]);
const output = resolve(args[1]);
if (source === output || output.startsWith(source + "/") || source.startsWith(output + "/")) {
  throw new Error("Source and output directories must not overlap");
}
const build = JSON.parse(await readFile(resolve(source, "build.json"), "utf8"));
if (typeof build.id !== "string" || !build.id) throw new Error("Missing UI build id");
await mkdir(resolve(output, "assets"), { recursive: true });
for (const name of ["app.js", "app.css", "static-worker.js"]) {
  await copyFile(resolve(source, name), resolve(output, "assets", name));
}
await copyFile(resolve(here, "worker.mjs"), resolve(output, "_worker.js"));
await writeFile(resolve(output, "_routes.json"), JSON.stringify({ version: 1, include: ["/*"], exclude: [] }));
await writeFile(resolve(output, "build.json"), JSON.stringify(build) + "\n");
