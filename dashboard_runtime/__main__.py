"""CLI: core commands need only Python 3.10+; MCP and UI builds are optional."""

from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path
from .model import DashboardError
from .service import Service, TOOLS
from .lifecycle import DEFAULT_IDLE_TIMEOUT


def parser():
    p = argparse.ArgumentParser(prog="charts-design-runtime")
    p.add_argument(
        "--root",
        default=".charts-runtime",
        help="Persistent dashboard store (shared by all transports)",
    )
    p.add_argument("--project-root", help="Default project containing data and dashboard assets; MCP requests can select another projectRoot")
    p.add_argument("--runtime-root", help="Disposable runtime cache and diagnostics directory")
    p.add_argument("--sources", help="Operator-owned read-only source aliases JSON")
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("id")
    init.add_argument("--title")
    init.add_argument("--demo", action="store_true")
    init.add_argument(
        "--mode",
        choices=["dashboard", "report"],
        default="dashboard",
        help="Initial view; report provides a Markdown document with inline chart fences",
    )
    migration = sub.add_parser('migrate-project')
    migration.add_argument('--source-root', required=True)
    migration.add_argument('--board', action='append', required=True)
    migration.add_argument('--apply', action='store_true')
    sub.add_parser("list")
    for name in ("get", "validate", "history"):
        sub.add_parser(name).add_argument("id")
    patch = sub.add_parser("patch")
    patch.add_argument("id")
    patch.add_argument("--expected", type=int, required=True)
    patch.add_argument("--file", required=True)
    restore = sub.add_parser("restore")
    restore.add_argument("id")
    restore.add_argument("--expected", type=int, required=True)
    restore.add_argument("--revision", type=int, required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--idle-timeout",
        type=float,
        default=DEFAULT_IDLE_TIMEOUT,
        help="Exit after this many idle seconds (default: 60)",
    )
    export = sub.add_parser("export")
    export.add_argument("id")
    export.add_argument("--output", required=True)
    export.add_argument("--format", choices=["json", "html", "csv"], default="html")
    export.add_argument("--dataset", help="Dataset ID for a complete streaming CSV export")
    export.add_argument("--component", help="Table component ID for a complete streaming CSV export")
    imported = sub.add_parser("import")
    imported.add_argument("id")
    imported.add_argument("--file", required=True)
    legacy = sub.add_parser("import-workspace")
    legacy.add_argument("id")
    legacy.add_argument("--path", required=True)
    call = sub.add_parser("call")
    call.add_argument("tool", choices=list(TOOLS))
    call.add_argument("--json-file", default="-")
    sub.add_parser("catalog")
    sub.add_parser("contract")
    mcp = sub.add_parser("mcp")
    mcp.add_argument(
        "--idle-timeout",
        type=float,
        default=DEFAULT_IDLE_TIMEOUT,
        help="Exit after this many idle seconds (default: 60)",
    )
    server = sub.add_parser(
        "server",
        help="Self-hosted server: remote Streamable HTTP MCP plus browser previews (see docs/operations/self-hosted-server.md)",
    )
    for target in (server, sub.add_parser("share", help="Print an expiring browser link for one dashboard on a server workspace")):
        target.add_argument("--workspace", help="Directory holding one sub-directory per project (env CHARTS_WORKSPACE)")
        target.add_argument("--public-url", help="External base URL used in links, e.g. https://charts.example.com (env CHARTS_PUBLIC_URL)")
        target.add_argument("--token", action="append", help="Bearer token accepted on /mcp; repeat to rotate (env CHARTS_SERVER_TOKENS)")
        target.add_argument("--token-file", help="File with one bearer token per line (env CHARTS_SERVER_TOKEN_FILE)")
        target.add_argument("--share-ttl-hours", type=float, help="Default lifetime of browser links (default 168)")
        target.add_argument("--default-project", help="Project used when a call omits projectRoot (default: default)")
        target.add_argument("--host", help="Bind address (default 127.0.0.1; use 0.0.0.0 in containers)")
        target.add_argument("--port", type=int, help="Port (default 8000)")
        target.add_argument("--stateless", action="store_true", help="Stateless MCP sessions for load-balanced replicas")
        target.add_argument("--allowed-host", action="append", help="Extra Host header accepted by /mcp")
        target.add_argument("--forwarded-allow-ips", help="Reverse proxies trusted for X-Forwarded-* (default 127.0.0.1)")
    server.add_argument("--insecure-no-auth", action="store_true", help="Loopback-only trial without tokens")
    share = sub.choices["share"]
    share.add_argument("project")
    share.add_argument("dashboard")
    share.add_argument("--access", choices=["view", "edit"], default="view")
    share.add_argument("--hours", type=float, help="Link lifetime in hours")
    return p


def server_command(args):
    from .server import Links, ShareState, Signer, WorkspaceProjects, serve, settings_from_args
    if args.command == "server":
        serve(settings_from_args(args))
        return None
    # Links are signed with the server secret; minting one needs no bearer token.
    args.insecure_no_auth = False
    settings = settings_from_args(args)
    projects = WorkspaceProjects(settings)
    project = projects.name(args.project)
    if not projects.exists(project):
        raise DashboardError("NOT_FOUND", "Project not found in the server workspace")
    projects.service(project).store.revision(args.dashboard)
    links = Links(settings, Signer(settings.secret), ShareState(settings.runtime / "server-state.sqlite3"))
    return {"dashboardId": args.dashboard, "project": project, **links.share(project, args.dashboard, args.access, args.hours)}


def read_json(path):
    return json.load(sys.stdin) if path == "-" else json.loads(Path(path).read_text())


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command in ("server", "share"):
            result = server_command(args)
            if result is not None:
                print(json.dumps(result, ensure_ascii=False))
            return 0
        service = Service(args.runtime_root or args.root, args.sources, project_root=args.project_root)
        if not args.project_root and args.command != 'mcp':
            print("Legacy --root mode: migrate to --project-root; new CLI dashboards require a project.", file=sys.stderr)
            if args.command in ("init", "import", "import-workspace"):
                raise DashboardError("PROJECT_REQUIRED", "Specify --project-root for new dashboards")
        command = args.command
        if command == 'migrate-project':
            from .project_migration import migrate_project
            if not args.project_root:
                raise DashboardError('PROJECT_REQUIRED', 'Migration requires --project-root')
            result = migrate_project(args.source_root, args.project_root, args.runtime_root or args.root, args.board, args.apply)
        elif command == "init":
            from .demo import executive_document, report_document
            from .model import apply_operations, new_document

            title = args.title or (
                "Analysis report" if args.mode == "report" else "Dashboard"
            )
            doc = (
                (report_document if args.mode == "report" else executive_document)(args.id)
                if args.demo
                else new_document(args.id, title)
            )
            if args.title is not None:
                doc["manifest"]["title"] = args.title
            if args.mode == "report" and doc["manifest"].get("viewMode") != "report":
                doc = apply_operations(
                    doc, [{"op": "set_view_mode", "value": "report"}]
                )
            result = service.call(
                "dashboard_create", {"dashboardId": args.id, "document": doc}
            )
        elif command in ("list", "get", "validate", "history"):
            result = service.call(
                "dashboard_" + command,
                {"dashboardId": args.id} if hasattr(args, "id") else {},
            )
        elif command == "patch":
            result = service.call(
                "dashboard_patch",
                {
                    "dashboardId": args.id,
                    "expectedRevision": args.expected,
                    "operations": read_json(args.file),
                },
            )
        elif command == "restore":
            result = service.call(
                "dashboard_restore",
                {
                    "dashboardId": args.id,
                    "expectedRevision": args.expected,
                    "revision": args.revision,
                },
            )
        elif command == "call":
            result = service.call(args.tool, read_json(args.json_file))
        elif command == "catalog":
            result = service.call("chart_catalog", {})
        elif command == "contract":
            from .contract import CONTRACT

            result = CONTRACT
        elif command == "import":
            result = service.call(
                "dashboard_create",
                {"dashboardId": args.id, "document": read_json(args.file)},
            )
        elif command == "import-workspace":
            from .legacy import import_workspace

            doc, notes = import_workspace(args.path, args.id)
            result = service.call(
                "dashboard_create", {"dashboardId": args.id, "document": doc}
            )
            result["migrationNotes"] = notes
        elif command == "export":
            doc = service.store.get(args.id, hydrate=False)
            path = Path(args.output).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            if args.format == 'csv':
                import shutil
                exported = service.call('dataset_export', {'dashboardId': args.id, 'datasetId': args.dataset, 'componentId': args.component})['export']
                shutil.copyfile(exported['path'], path)
                print(json.dumps({'output': str(path.resolve()), 'revision': doc['revision'], 'format': 'csv', **{k: v for k, v in exported.items() if k != 'path'}}))
                return 0
            if args.format == 'html':
                exported = service.call('dashboard_export', {'dashboardId': args.id, 'format': 'html'})['export']
                content = Path(exported['path']).read_text(encoding='utf-8')
            else:
                doc = service.store.hydrate(doc)
                content = json.dumps(doc, ensure_ascii=False, indent=2)
            path.write_text(content)
            result = {
                "output": str(path.resolve()),
                "revision": doc["revision"],
                "format": args.format,
            }
        elif command == "serve":
            from .http_server import RuntimeHTTPServer
            from .assets import render_html

            render_html("web")
            server = RuntimeHTTPServer(
                service, args.port, idle_timeout=args.idle_timeout
            )
            print(
                json.dumps(
                    {
                        "url": f"http://127.0.0.1:{server.server_address[1]}/#token={server.token}",
                        "mode": "local-only",
                    }
                ),
                flush=True,
            )
            try:
                server.serve_forever()
            finally:
                server.server_close()
            return 0
        elif command == "mcp":
            asyncio.run(
                __import__("dashboard_runtime.mcp_server", fromlist=["run"]).run(
                    service, args.idle_timeout
                )
            )
            return 0
        else:
            raise ValueError(f'Unsupported command: {command}')
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except DashboardError as exc:
        print(json.dumps(exc.as_dict(), ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": {"code": "COMMAND_FAILED", "message": str(exc)}}
            ),
            file=sys.stderr,
        )
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
