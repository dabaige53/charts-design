// Explicit release-resource step. Builds never rewrite design assets.
import { readFile, mkdir, copyFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { createHash } from "node:crypto";
const root = fileURLToPath(new URL("..", import.meta.url));
const dist = path.join(root, "dist");
const [js, css, worker, manifest] = await Promise.all(
  ["app.js", "app.css", "static-worker.js", "build.json"].map((name) =>
    readFile(path.join(dist, name)),
  ),
);
const id = createHash("sha256")
  .update(js)
  .update(css)
  .update(worker)
  .digest("hex")
  .slice(0, 16);
if (JSON.parse(manifest).id !== id) throw Error("构建资源不完整，请重新构建。");
const destination = path.resolve(root, "../dashboard_runtime/web/dist");
await mkdir(destination, { recursive: true });
for (const name of ["app.js", "app.css", "static-worker.js", "build.json"])
  await copyFile(path.join(dist, name), path.join(destination, name));
console.log(
  JSON.stringify({
    destination,
    id,
    files: ["app.js", "app.css", "static-worker.js", "build.json"],
  }),
);
