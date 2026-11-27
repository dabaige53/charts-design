import { copyFile, mkdir, writeFile } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
if (args.length !== 1) {
  console.error("Usage: bun deploy/pages/build.mjs <output-directory>");
  process.exit(1);
}
const output = resolve(args[0]);
await mkdir(output, { recursive: true });
await copyFile(resolve(here, "worker.mjs"), resolve(output, "_worker.js"));
await writeFile(resolve(output, "_routes.json"), JSON.stringify({ version: 1, include: ["/*"], exclude: [] }));
