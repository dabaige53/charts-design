import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { assetManifest, bundlePath, pagesAsset, releasePath, workerBundle } from "./deployment.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const withD1 = args[1] === "--d1";
if (args.length !== (withD1 ? 2 : 1)) {
  console.error("Usage: bun deploy/pages/build.mjs <output-directory> [--d1]");
  process.exit(1);
}
const output = resolve(args[0]);
await mkdir(output, { recursive: true });
const bundle = await Bun.build({ entrypoints: [resolve(here, "worker.mjs")], target: "browser",
  minify: true, naming: "_worker.js" });
if (!bundle.success) throw new AggregateError(bundle.logs, "Pages worker build failed");
await Bun.write(resolve(output, "_worker.js"), bundle.outputs[0]);
if (withD1) {
  const source = resolve(here, "../../runtime-ui/dist");
  const target = resolve(output, "runtime");
  const { id, webId, fonts } = JSON.parse(await readFile(resolve(source, "build.json"), "utf8"));
  if (!id) throw Error("Missing UI build version. Run bun run ui:prepare.");
  await mkdir(target, { recursive: true });
  const names = ["app.js", "app.css", "static-worker.js", "build.json"];
  for (const name of names)
    await copyFile(resolve(source, name), resolve(target, name));
  const web = webId ? [...names.slice(0, 3), ...fonts] : [];
  for (const name of web) {
    const destination = resolve(target, webId, name);
    await mkdir(dirname(destination), { recursive: true });
    await copyFile(resolve(source, "web", name), destination);
  }
  await writeFile(resolve(output, "." + bundlePath), await workerBundle(await readFile(resolve(output, "_worker.js"))));
  const runtime = await Promise.all([...names.map(name => "/runtime/" + name), ...web.map(name => "/runtime/" + webId + "/" + name), bundlePath].map(async name =>
    pagesAsset(name, await readFile(resolve(output, "." + name)))));
  await writeFile(resolve(output, "." + releasePath), JSON.stringify(assetManifest(runtime)));
}
await writeFile(resolve(output, "_routes.json"), JSON.stringify({ version: 1, include: ["/*"], exclude: [] }));
