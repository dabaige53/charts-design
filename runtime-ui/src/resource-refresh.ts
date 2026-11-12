import { useEffect } from "react";
import type { ToolCall } from "./types";

export function useVisibleVersionCheck({
  call, dashboardId, revision, buildId, blocked, staticMode, reload, setError,
}: {
  call: ToolCall; dashboardId: string; revision: number; buildId?: string;
  blocked: boolean; staticMode: boolean; reload: () => Promise<unknown>;
  setError: (message: string) => void;
}) {
  useEffect(() => {
    if (staticMode) return;
    let live = true;
    const check = () => {
      if (document.visibilityState !== "visible") return;
      void call("runtime_info", { dashboardId }).then((info) => {
        if (!live) return;
        if (buildId && info.uiBuildId && info.uiBuildId !== buildId) {
          setError("界面已更新，请重新打开看板预览。");
          return;
        }
        if (info.dashboardRevision && info.dashboardRevision !== revision) {
          if (blocked) setError("看板已更新，请完成当前操作后重新加载。");
          else void reload();
        }
      }).catch((error) => { if (live) setError(String(error)); });
    };
    document.addEventListener("visibilitychange", check);
    return () => {
      live = false;
      document.removeEventListener("visibilitychange", check);
    };
  }, [call, dashboardId, revision, buildId, blocked, staticMode, reload, setError]);
}
