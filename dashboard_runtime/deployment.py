"""Portable static website and rebuildable source; no runtime database references."""

import copy
import hashlib
import html
import json
import shutil
import uuid
from pathlib import Path
from .model import require
from .assets import DIST
from .build import BACKEND_BUILD_ID


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
        encoding="utf-8",
    )


def export_site(store, board):
    doc = copy.deepcopy(store.get(board, hydrate=False))
    base = (
        getattr(store, "project_root", store.root)
        / "deployments"
        / (board + "-" + uuid.uuid4().hex[:12])
    )
    site = base / "dist"
    site.mkdir(parents=True)
    root = Path(__file__).resolve().parent.parent
    require(
        (root / "runtime-ui/generated/original-engine.mjs").exists(),
        "Build the runtime before exporting source",
        "ASSETS_NOT_BUILT",
    )
    refs = doc["snapshot"].pop("datasetRefs", {})
    table_refs = doc["snapshot"].pop("componentDataRefs", {})
    doc.pop("computed", None)
    doc.pop("progressive", None)
    doc["snapshot"].pop("localMode", None)
    doc["manifest"]["annotations"] = []
    doc["manifest"].pop("originalWorkspace", None)
    # Publish labels, not local connection names, SQL, parameters or file paths.
    doc["manifest"]["sources"] = {
        key: {"id": key, "name": value.get("name", key), "kind": "file"}
        for key, value in doc["manifest"].get("sources", {}).items()
    }
    files, counts = {}, {}
    options = {f["id"]: {} for f in doc["manifest"]["filters"] if f["op"] == "in"}
    for cid, ref in table_refs.items():
        key = "component-" + cid
        refs[key] = ref
        c = doc["manifest"]["components"][cid]
        c["datasetId"] = key
        c.setdefault("binding", {})
        c["config"].pop("rowsRef", None)
    used = {c.get("datasetId") for c in doc["manifest"]["components"].values()} - {None}
    refs = {k: v for k, v in refs.items() if k in used}
    datasets = {
        k: v for k, v in doc["snapshot"].get("datasets", {}).items() if k in used
    }
    doc["manifest"]["datasets"] = {
        k: v for k, v in doc["manifest"]["datasets"].items() if k in used
    }
    doc["manifest"]["metrics"] = {
        k: v
        for k, v in doc["manifest"]["metrics"].items()
        if v.get("datasetId") in used
    }
    for key in sorted(set(datasets) | set(refs)):
        rows = store.data.iter_rows(refs[key]) if key in refs else iter(datasets[key])
        paths = []
        chunk = []
        size = 2
        count = 0
        related = [
            f
            for f in doc["manifest"]["filters"]
            if f["id"] in options
            and any(
                doc["manifest"]["components"][cid].get("datasetId") == key
                for cid in f["componentIds"]
            )
        ]

        def flush():
            if not chunk:
                return
            name = (
                "data/"
                + hashlib.sha256(key.encode()).hexdigest()[:16]
                + "-"
                + str(len(paths))
                + ".json"
            )
            write(site / name, chunk)
            paths.append(name)

        for row in rows:
            encoded = len(json.dumps(row, ensure_ascii=False).encode())
            require(
                encoded < 8_000_000, "One data row exceeds static export size limit"
            )
            if chunk and size + encoded > 4_000_000:
                flush()
                chunk = []
                size = 2
            chunk.append(row)
            size += encoded + 1
            count += 1
            for f in related:
                v = row.get(f["field"])
                options[f["id"]][json.dumps(v, ensure_ascii=False)] = v
        flush()
        files[key] = paths
        counts[key] = count
    doc["snapshot"]["datasets"] = {}
    doc["staticFiles"] = files
    doc["staticFilterOptions"] = {
        key: list(values.values()) for key, values in options.items()
    }
    from .statistical import statistical_artifacts

    original = store.get(board, hydrate=False)
    artifacts = statistical_artifacts(store.statistical_document(original))
    write(site / "document.json", {"document": doc, "statisticalArtifacts": artifacts})
    (site / "assets").mkdir()
    for name in ("app.js", "app.css"):
        shutil.copy2(DIST / name, site / "assets" / name)
    (site / "index.html").write_text(
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dashboard</title><link rel="stylesheet" href="./assets/app.css"></head><body><script>window.__DASHBOARD_BOOT__={mode:"static",documentUrl:"./document.json"};</script><script src="./assets/app.js"></script></body></html>'.replace(
            "<title>Dashboard</title>",
            "<title>" + html.escape(doc["manifest"]["title"]) + "</title>",
        )
    )
    (site / "_headers").write_text(
        "/*\n  Cache-Control: no-cache\n  X-Content-Type-Options: nosniff\n"
    )
    if (root / "LICENSE").exists():
        shutil.copy2(root / "LICENSE", base / "LICENSE")
    source = base / "source"
    shutil.copytree(
        root / "dashboard_runtime/web",
        source / "dashboard_runtime/web",
        ignore=shutil.ignore_patterns("dist", "node_modules"),
    )
    for name in ("entry.mjs", "echarts.mjs", "report-markdown.mjs", "host-app.mjs"):
        (source / "runtime-ui").mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / "runtime-ui" / name, source / "runtime-ui" / name)
    shutil.copytree(root / "runtime-ui/generated", source / "runtime-ui/generated")
    pkg = json.loads((root / "runtime-ui/package.json").read_text())
    pkg["name"] = "standalone-dashboard"
    pkg["scripts"] = {
        "build": "node build.mjs",
        "deploy:cloudflare": "npx wrangler pages deploy dist",
    }
    write(base / "package.json", pkg)
    lock = root / "runtime-ui/package-lock.json"
    if lock.exists():
        data = json.loads(lock.read_text())
        data["name"] = pkg["name"]
        data["packages"][""]["name"] = pkg["name"]
        write(base / "package-lock.json", data)
    (base / "build.mjs").write_text(
        "import {build} from 'esbuild';\nawait build({entryPoints:['source/runtime-ui/entry.mjs'],bundle:true,format:'iife',target:['es2022'],outfile:'dist/assets/app.js',minify:true,legalComments:'eof',loader:{'.woff2':'dataurl','.woff':'dataurl'}});\n"
    )
    write(
        base / "export-manifest.json",
        {
            "dashboardId": board,
            "revision": doc["revision"],
            "backendBuildId": BACKEND_BUILD_ID,
            "datasets": counts,
            "dataScope": "all rows of datasets used by components",
            "annotations": "excluded",
            "runtime": "static browser only",
        },
    )
    (base / "README.md").write_text("""# 独立看板网页

`dist/` 是可直接部署的静态网站，含完整数据，不需要 MCP、Codex、Python 或数据库。

- 发布：将 `dist/` 上传到任意静态网站；Cloudflare Pages 可直接上传该目录，或运行 `npm run deploy:cloudflare -- --project-name <已有项目名>`。
- 本地预览：通过任意静态 HTTP 服务打开 `dist/`。数据通过相对 URL 读取，不使用 file:// 双击方式。
- 修改与重建：`npm ci`，编辑 `source/` 或 `dist/document.json`，运行 `npm run build`。源码和固定依赖随包保留，无需原 MCP 仓库。
- 数据：`dist/data/` 为导出时的数据版本，包含页面所用数据集的全部数据行。浏览器按组件读取所需数据集，筛选、排序、表格分页在本地计算。数据集首次使用时会读取该数据集的所有分片。
- 网站为只读设计；支持阅读与筛选，不连接原项目的编辑、批注保存或数据刷新接口。批注默认不发布。统计 SVG 保留导出时计算结果。
- 只有 `dist/` 是网站发布目录。完整源码压缩包用于维护，不应当作网站目录上传。

Cloudflare 官方说明：https://developers.cloudflare.com/pages/get-started/direct-upload/
""")
    shutil.make_archive(str(base / "site"), "zip", site)
    archive = shutil.make_archive(str(base.parent / base.name), "zip", base)
    return {
        "export": {
            "path": archive,
            "directory": str(base),
            "siteArchive": str(base / "site.zip"),
            "publishDirectory": str(site),
            "revision": doc["revision"],
            "datasetRows": counts,
            "requiresMcp": False,
            "includesSource": True,
        }
    }
