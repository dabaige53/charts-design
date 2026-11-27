import { DurableObject } from "cloudflare:workers";
import { WorkspaceCheckpoint } from "./checkpoint.mjs";

export class ChartsWorkspace extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.checkpoint = new WorkspaceCheckpoint(ctx.storage);
    this.queue = Promise.resolve();
    this.ready = false;
  }

  run(action) {
    const next = this.queue.then(async () => {
      const container = this.ctx.container;
      try {
        if (!this.ready || !container.running) {
          if (container.running) await container.destroy();
          if (!this.env.CHARTS_SERVER_TOKENS || !this.env.CHARTS_PUBLIC_URL?.startsWith("https://"))
            throw new Error("Configure the HTTPS origin and server token");
          container.start({
            image: container.images.base, instance: "standard-1", enableInternet: false,
            entrypoint: ["sh", "-ec", "while [ ! -f /tmp/workspace-ready ]; do sleep .1; done; exec python -m dashboard_runtime server"],
            env: {
              CHARTS_SERVER_TOKENS: this.env.CHARTS_SERVER_TOKENS, CHARTS_PUBLIC_URL: this.env.CHARTS_PUBLIC_URL,
              CHARTS_STORAGE_BACKEND: "cloudflare", CHARTS_STATELESS: "1",
              CHARTS_RELEASE_COMMIT: this.env.CHARTS_RELEASE_COMMIT || "",
              CHARTS_RELEASE_VERSION: this.env.CHARTS_RELEASE_VERSION || "",
            },
          });
          await container.setInactivityTimeout(300_000);
          await this.checkpoint.restore(container);
          const start = await container.exec(["touch", "/tmp/workspace-ready"]);
          if (await start.exitCode !== 0) throw new Error("Runtime startup failed");
          const probe = await container.exec(["/app/.venv/bin/python", "-c",
            "import socket,time\nfor attempt in range(240):\n try:\n  socket.create_connection(('127.0.0.1',8000),1).close(); break\n except OSError: time.sleep(.25)\nelse: raise SystemExit(1)"],
          { stdout: "ignore", stderr: "ignore" });
          if (await probe.exitCode !== 0) throw new Error("Runtime unavailable");
          await this.checkpoint.save(container);
          this.ready = true;
        }
        return await action(container);
      } catch (error) {
        this.ready = false;
        throw error;
      }
    });
    this.queue = next.catch(() => {});
    return next;
  }

  fetch(request) {
    return this.run(async container => {
      const url = new URL(request.url);
      const path = url.pathname;
      url.protocol = "http:";
      const forwarded = new Request(url, request);
      const response = await container.getTcpPort(8000).fetch(new Request(forwarded, { redirect: "manual" }));
      const annotationWrite = request.method === "POST" && path.match(/^\/s\/([0-9a-f]{32})\/api\/annotations$/);
      if (annotationWrite && response.ok) {
        await this.checkpoint.saveAnnotations(container, annotationWrite[1]);
      } else if (["POST", "DELETE"].includes(request.method) && !path.startsWith("/s/") && response.ok) {
        await this.checkpoint.save(container);
      }
      return response;
    });
  }

  cleanup() {
    return this.run(async container => {
      const job = await container.exec(["/app/.venv/bin/python", "-m", "dashboard_runtime.cloudflare_shares"], {
        cwd: "/app", env: { CHARTS_RUNTIME_ROOT: "/data/runtime", CHARTS_STORAGE_BACKEND: "cloudflare" },
        stdout: "ignore", stderr: "ignore", user: "10001:10001",
      });
      if (await job.exitCode !== 0) throw new Error("Share cleanup failed");
      await this.checkpoint.save(container);
    });
  }
}

export default {
  fetch(request, env) {
    if (new URL(request.url).origin !== env.CHARTS_PUBLIC_URL) return new Response(null, { status: 404 });
    return env.CHARTS.getByName("workspace").fetch(request);
  },
  async scheduled(event, env) {
    await env.CHARTS.getByName("workspace").cleanup();
  },
};
