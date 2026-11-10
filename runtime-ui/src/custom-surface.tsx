import { useEffect, useMemo, useRef, useState } from "react";
import { RecoveryAlert } from "./recovery-alert";
import type { Config } from "./types";

// Executable author content stays in an opaque-origin frame, never in the host React tree.
export function CustomSurface({ config, title }: { config: Config; title: string }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const source = useMemo(() => {
    const data = JSON.stringify(config.data ?? {}).replaceAll("<", "\\u003c");
    return `<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' https: blob:; style-src 'unsafe-inline' https:; img-src https: data: blob:; font-src https: data:; connect-src https:; media-src https: data: blob:; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<style>html,body{margin:0;width:100%;height:100%;font-family:system-ui,sans-serif}*{box-sizing:border-box}</style>
<script>
window.chartData=${data};
const report=message=>parent.postMessage({type:"charts:custom-error",message:String(message).slice(0,2000)},"*");
addEventListener("error",event=>report(event.message||"自定义组件资源加载失败"),true);
addEventListener("unhandledrejection",event=>report(event.reason?.message||event.reason));
</script></head><body>${config.html}</body></html>`;
  }, [config.html, config.data]);
  useEffect(() => {
    setError("");
    const receive = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow) return;
      if (event.data?.type === "charts:custom-error" && typeof event.data.message === "string")
        setError(event.data.message.slice(0, 2000));
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [source, attempt]);
  return (
    <div className="relative flex min-h-0 w-full flex-1 flex-col">
      {error && <RecoveryAlert title="自定义组件运行失败" message={error}
        onRetry={() => setAttempt((value) => value + 1)} retryLabel="重新运行" />}
      <iframe key={attempt} ref={frame} title={title} srcDoc={source}
        sandbox="allow-scripts" referrerPolicy="no-referrer"
        className="min-h-0 w-full flex-1 border-0" />
    </div>
  );
}
