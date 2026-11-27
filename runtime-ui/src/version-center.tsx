import React, { useCallback, useEffect, useRef, useState } from "react";
import { Check, Eye, ExternalLink, MessageSquareText, RefreshCw, RotateCcw, Save, Send, Trash2 } from "lucide-react";
import { Button } from "./ui";
import { Input } from "./components/ui/input";
import { Badge } from "./components/ui/badge";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "./components/ui/sheet";
import type { Config, Document, ToolCall } from "./types";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "./components/ui/dialog";
import { DashboardApp } from "./dashboard";
import { createVersionReader } from "./cos-client";

export function VersionCenter({ open, onOpenChange, document, call, onRestore, onSaved, publicationApiBase, requestHeaders, browserWorkspaceUrl, onOpenBrowser, shareScope }: {
  open: boolean; onOpenChange: (open: boolean) => void; document: Document;
  call: ToolCall; onRestore: (revision: number) => Promise<void>; onSaved: () => Promise<void>;
  publicationApiBase?: string;
  requestHeaders?: () => Record<string, string>;
  browserWorkspaceUrl?: string;
  onOpenBrowser?: (url: string) => Promise<void>;
  shareScope?: string | null;
}) {
  const [status, setStatus] = useState<Config | null>(null);
  const [history, setHistory] = useState<Config[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [pendingAction, setPendingAction] = useState("");
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<Document | null>(null);
  const [deleteRevision, setDeleteRevision] = useState<number | null>(null);
  const [deletePlan, setDeletePlan] = useState<Config | null>(null);
  const [deleteResult, setDeleteResult] = useState<Config | null>(null);
  const previewSequence = useRef(0);
  const [tab, setTab] = useState<"versions" | "shares">("versions");
  const [shares, setShares] = useState<Config[]>([]);
  const [expiration, setExpiration] = useState("7d");
  const [annotationMode, setAnnotationMode] = useState<"view" | "annotate">("view");
  const [newShare, setNewShare] = useState<Config | null>(null);
  const [feedback, setFeedback] = useState<Config | null>(null);
  const [publishWithShare, setPublishWithShare] = useState(false);
  const pendingShare = useRef<{ target: string; requestId: string; expectedRevision: number } | null>(null);
  const pendingShareKey = `charts-share-request:${JSON.stringify([shareScope || publicationApiBase || window.location.pathname, document.id])}`;
  useEffect(() => {
    pendingShare.current = null;
    try {
      const saved = JSON.parse(window.sessionStorage.getItem(pendingShareKey) || "null");
      if (typeof saved?.target === "string" && typeof saved?.requestId === "string" && Number.isInteger(saved?.expectedRevision)) {
        pendingShare.current = saved;
        const target = JSON.parse(saved.target);
        if (["7d", "30d", "never"].includes(target[2])) setExpiration(target[2]);
        if (["view", "annotate"].includes(target[3])) setAnnotationMode(target[3]);
      }
    } catch { /* Keep in-memory retries available when browser storage is unavailable. */ }
  }, [pendingShareKey]);
  const rememberPendingShare = (value: typeof pendingShare.current) => {
    pendingShare.current = value;
    try {
      if (value) window.sessionStorage.setItem(pendingShareKey, JSON.stringify(value));
      else window.sessionStorage.removeItem(pendingShareKey);
    } catch { /* The current tab still retains the original idempotency key. */ }
  };
  const refresh = useCallback(async () => {
    const [versions, saved] = await Promise.all([
      call("dashboard_version_status", { dashboardId: document.id }),
      call("dashboard_history", { dashboardId: document.id, limit: 100 }),
    ]);
    setStatus(versions);
    const entries = new Map<number, Config>((saved.history || []).map((item: Config) => [item.revision, item]));
    for (const release of versions.releases || []) {
      if (!entries.has(release.revision)) entries.set(release.revision, { ...release, name: "", action: "release" });
    }
    setHistory([...entries.values()].sort((a, b) => b.revision - a.revision));
  }, [call, document.id]);
  useEffect(() => {
    if (!open) return;
    setError(""); setPreview(null); setDeleteRevision(null); setDeletePlan(null); setNewShare(null);
    previewSequence.current++;
    void refresh().catch((e) => setError(String(e.message || e)));
    return () => { previewSequence.current++; };
  }, [open, refresh]);
  useEffect(() => {
    if (!open || !deleteResult?.id || deleteResult.state !== "deleting") return;
    let live = true;
    const timer = setTimeout(() => {
      void call("dashboard_version_delete_status", { dashboardId: document.id, jobId: deleteResult.id })
        .then(async (result) => { if (live) { setDeleteResult(result); await refresh(); } })
        .catch((e) => { if (live) setError(String(e.message || e)); });
    }, 1500);
    return () => { live = false; clearTimeout(timer); };
  }, [open, deleteResult, call, document.id, refresh]);
  const run = async (work: () => Promise<void>, message = "") => {
    setBusy(true); setError(""); setPendingAction(message);
    try { await work(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); setPendingAction(""); }
  };
  const loadShares = async () => {
    const result = await call("dashboard_share_status", { dashboardId: document.id });
    setShares(result.shares);
  };
  const quickPublish = async (revision?: number, withShare = false) => {
    const args: Config = { dashboardId: document.id, expectedRevision: status?.draftRevision };
    if (revision !== undefined) args.revision = revision;
    if (withShare) {
      const target = JSON.stringify([document.id, revision, expiration, annotationMode]);
      if (target !== pendingShare.current?.target) {
        rememberPendingShare({ target, requestId: crypto.randomUUID(), expectedRevision: args.expectedRevision });
      }
      args.expectedRevision = pendingShare.current!.expectedRevision;
      args.share = { expiration, annotationMode, requestId: pendingShare.current!.requestId };
    }
    const result = await call("dashboard_publish", args);
    if (!result.ok) throw Error(result.error?.message || "发布失败");
    setStatus(result.versionStatus);
    setHistory((items) => {
      const byRevision = new Map<number, Config>(items.map((item) => [item.revision, item]));
      for (const release of result.versionStatus.releases || []) {
        if (!byRevision.has(release.revision)) byRevision.set(release.revision, release);
      }
      return [...byRevision.values()].sort((a, b) => b.revision - a.revision);
    });
    if (result.shareError) throw Error(`版本 ${result.publishedRevision} 已发布。分享链接生成失败：${result.shareError.message}`);
    if (result.share) {
      setNewShare(result.share);
      rememberPendingShare(null);
    }
  };
  const openFeedback = async (share: Config, popup?: Window | null) => {
    let receipt = share;
    if (publicationApiBase) {
      const endpoint = new URL(`${publicationApiBase}${encodeURIComponent(share.shareId)}/feedback`, location.href);
      if (endpoint.origin !== location.origin) throw Error("分享反馈入口须与当前工作区同源");
      endpoint.searchParams.set("dashboardId", document.id);
      const response = await fetch(endpoint, { credentials: "same-origin", cache: "no-store", headers: requestHeaders?.() });
      const value = await response.json();
      if (!response.ok || value.ok === false) throw Error(value.error?.message || "无法读取分享反馈");
      receipt = { ...share, ...value };
    }
    const url = receipt.feedbackUrl || receipt.url;
    if (!url || !/^https?:$/.test(new URL(url, location.href).protocol)) throw Error("未取得可用的分享反馈地址");
    if (popup && !popup.closed) {
      popup.location.replace(url);
      return;
    }
    setFeedback({ ...receipt, feedbackUrl: url, loadedAt: Date.now() });
  };
  const openFeedbackWindow = (share: Config) => {
    const popup = window.open("about:blank", "_blank");
    if (popup) popup.opener = null;
    void run(async () => {
      try { await openFeedback(share, popup); }
      catch (failure) { popup?.close(); throw failure; }
    }, "正在读取分享反馈…");
  };
  return <><Sheet open={open} onOpenChange={onOpenChange}>
    <SheetContent className="overflow-y-auto sm:max-w-xl">
      <SheetHeader>
        <SheetTitle>版本与分享</SheetTitle>
        <SheetDescription>保存编辑成果，选择一个版本分享，并查看该分享收到的批注。</SheetDescription>
      </SheetHeader>
      <div className="flex flex-col gap-5 px-4 pb-6">
        <div className="flex gap-2" role="tablist" aria-label="版本与分享">
          <Button role="tab" aria-selected={tab === "versions"} variant={tab === "versions" ? "default" : "outline"}
            onClick={() => setTab("versions")}>版本</Button>
          <Button role="tab" aria-selected={tab === "shares"} variant={tab === "shares" ? "default" : "outline"}
            disabled={busy} onClick={() => { setTab("shares"); void run(loadShares); }}>分享</Button>
        </div>
        {error && <p role="alert" className="text-destructive">{error}</p>}
        {pendingAction && <p role="status">{pendingAction}</p>}
        {newShare && <div className="rounded-lg border p-3">
          <a className="break-all text-primary underline underline-offset-4" href={newShare.accessUrl || newShare.url}
            target="_blank" rel="noreferrer">{newShare.accessUrl || newShare.url}</a>
          <p className="mt-2">访问密钥：<strong>{newShare.accessKey}</strong></p>
          <p className="mt-1 text-xs text-muted-foreground">请保存密钥；关闭后无法再次查看。</p>
          <p className="mt-1 text-xs text-muted-foreground">{newShare.annotationMode === "annotate" ? "可批注" : "仅查看"} · 内容固定在分享时的版本</p>
        </div>}
        <fieldset className="flex flex-wrap gap-3">
          <legend className="mb-2 text-sm font-medium">分享设置</legend>
          <select aria-label="分享有效期" className="h-8 border bg-background px-3" disabled={busy}
            value={expiration} onChange={(event) => setExpiration(event.target.value)}>
            <option value="7d">7 天过期</option><option value="30d">30 天过期</option><option value="never">不过期</option>
          </select>
          <select aria-label="分享权限" className="h-8 border bg-background px-3" disabled={busy}
            value={annotationMode} onChange={(event) => setAnnotationMode(event.target.value as "view" | "annotate")}>
            <option value="view">仅查看</option><option value="annotate">可批注</option>
          </select>
        </fieldset>
        {deleteResult?.state === "complete" && <p role="status">已删除，专属文件清理完成。</p>}
        {(status?.deletionJobs || []).map((job: Config) => <div key={job.id} role="status" className="rounded-lg border p-3">
          <p>版本 {job.revision} · {job.state === "failed" ? "访问已撤销，文件清理未完成" : "正在删除文件"}</p>
          {job.error && <p className="text-sm text-destructive">{job.error}</p>}
          <Button variant="outline" disabled={busy} onClick={() => void run(async () => {
            setDeleteResult(await call("dashboard_version_delete_retry", { dashboardId: document.id, jobId: job.id }));
            await refresh();
          })}>继续清理</Button>
        </div>)}
        {tab === "versions" ? <>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">草稿 {status?.draftRevision ?? document.revision}</Badge>
            <Badge variant="outline">已保存 {status?.savedRevision ?? "—"}</Badge>
            <Badge>当前发布 {status?.publishedRevision ?? "未发布"}</Badge>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button disabled={busy || !status} onClick={() => void run(() => quickPublish(undefined, publishWithShare), "正在发布…")}>
              发布当前草稿
            </Button>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={publishWithShare} disabled={busy} onChange={(event) => setPublishWithShare(event.target.checked)} />
              同时生成分享链接
            </label>
          </div>
          <div className="flex gap-2">
            <Input aria-label="版本名称" placeholder="版本名称（可选）" value={name} onChange={(e) => setName(e.target.value)} />
            <Button disabled={busy || !status} onClick={() => void run(async () => {
              const result = await call("dashboard_checkpoint", { dashboardId: document.id, expectedRevision: status?.draftRevision, name });
              if (!result.ok) throw new Error(result.error?.message || "保存检查未通过");
              setName(""); await refresh(); await onSaved();
            })}><Save />保存版本</Button>
          </div>
          <div className="flex flex-col gap-3">
            {history.map((item) => <article key={item.revision} className="rounded-lg border p-3">
              <div className="flex items-center justify-between gap-2">
                <strong>{item.name || `版本 ${item.revision}`}</strong>
                <Badge variant="outline">已冻结</Badge>
                {status?.publishedRevision === item.revision && <Badge><Check />当前发布</Badge>}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">版本 {item.revision} · {item.created_at}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" variant="outline" disabled={busy} onClick={() => void run(async () => {
                  const sequence = ++previewSequence.current;
                  const result = await call("dashboard_version_get", { dashboardId: document.id, revision: item.revision });
                  if (sequence === previewSequence.current) setPreview(result.version);
                })}><Eye />查看版本</Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => void run(async () => {
                  await onRestore(item.revision); await refresh(); setPreview(null);
                })}><RotateCcw />恢复为草稿</Button>
                <Button size="sm" disabled={busy || status?.publishedRevision === item.revision}
                  onClick={() => void run(() => quickPublish(item.revision), "正在发布…")}><Send />发布此版本</Button>
                <Button size="sm" variant="outline" disabled={busy}
                  onClick={() => void run(() => quickPublish(item.revision, true), `正在分享版本 ${item.revision}…`)}><ExternalLink />分享此版本</Button>
                <Button size="sm" variant="outline" className="text-destructive hover:text-destructive"
                  disabled={busy}
                  onClick={() => void run(async () => {
                    const current = await call("dashboard_version_status", { dashboardId: document.id });
                    setStatus(current);
                    const plan = await call("dashboard_version_delete_preview", {
                      dashboardId: document.id, expectedRevision: current.draftRevision, revision: item.revision,
                    });
                    setDeleteRevision(item.revision); setDeletePlan(plan); setDeleteResult(null);
                  }, "正在检查删除影响…")}><Trash2 />删除版本</Button>
              </div>
            </article>)}
          </div>
          {!!status?.releases?.length && <section>
            <h3 className="mb-2 font-medium">发布记录</h3>
            <ul className="space-y-2 text-sm text-muted-foreground">{status.releases.map((event: Config) =>
              <li key={event.id}>版本 {event.revision} · {event.created_at}</li>)}</ul>
          </section>}
        </> : <>
          <p className="text-sm text-muted-foreground">每个分享固定使用所选发布版本，批注分别保存。替换分享会生成新链接和新密钥，旧链接与旧会话失效；其他分享保持原样。</p>
          <div className="flex gap-2">
            <Button disabled={busy || !status?.publishedRevision} onClick={() => void run(async () => {
              const target = JSON.stringify([document.id, status?.publishedRevision, expiration, annotationMode]);
              if (target !== pendingShare.current?.target) rememberPendingShare({ target, requestId: crypto.randomUUID(), expectedRevision: status?.publishedRevision });
              const result = await call("dashboard_share_publish", { dashboardId: document.id,
                expectedRevision: pendingShare.current!.expectedRevision, expiration, annotationMode, requestId: pendingShare.current!.requestId });
              if (result.ok === false || !(result.accessUrl || result.url)) throw Error(result.error?.message || "分享链接生成失败");
              setNewShare(result); rememberPendingShare(null);
              await loadShares();
            })}>新建分享</Button>
          </div>
          {shares.map((share) => <article key={share.shareId} className="rounded-lg border p-3">
            <p>{share.pages?.length > 1 ? `包含 ${share.pages.length} 个页面 · ` : ""}版本 {share.revision} · {share.expiresAt ? new Date(share.expiresAt * 1000).toLocaleString() : "不过期"}</p>
            <p className="my-2 text-xs text-muted-foreground">{share.cleanupState === "pending" ? "等待云端清理" : share.state === "active" ? "可访问" : share.state}</p>
            <p className="mb-2 text-xs text-muted-foreground">{share.annotationMode === "annotate" ? "可批注" : "仅查看"}</p>
            {(publicationApiBase || /^https?:\/\//.test(share.feedbackUrl || "")) && <Button size="sm" variant="outline" className="mr-2"
              disabled={busy || share.state !== "active" || share.cleanupState === "pending"}
              onClick={() => openFeedbackWindow(share)}><MessageSquareText />查看读者批注</Button>}
            <Button size="sm" variant="outline" className="mr-2" disabled={busy || share.cleanupState === "pending" || !status?.publishedRevision} onClick={() => void run(async () => {
              const replacement = await call("dashboard_share_replace", {
                dashboardId: document.id, shareId: share.shareId, expectedRevision: status?.publishedRevision, expiration,
              });
              setNewShare(replacement);
              await loadShares();
              if (!replacement.previousRevoked) setError("新分享已创建，旧分享撤销失败。请保留新密钥，并再次撤销旧分享。");
            })}>替换为当前发布版本</Button>
            <Button size="sm" variant="outline" disabled={busy || share.cleanupState === "pending"} onClick={() => void run(async () => {
              await call("dashboard_share_delete", { dashboardId: document.id, shareId: share.shareId });
              setNewShare(null); await loadShares();
            })}>撤销分享</Button>
          </article>)}
          {browserWorkspaceUrl && !publicationApiBase && <Button variant="outline" disabled={busy}
            onClick={() => onOpenBrowser ? void run(() => onOpenBrowser(browserWorkspaceUrl))
              : window.open(browserWorkspaceUrl, "_blank", "noopener,noreferrer")}>
            <ExternalLink />在浏览器工作区查看分享反馈
          </Button>}
        </>}
      </div>
    </SheetContent>
  </Sheet>
  <Dialog open={deletePlan !== null} onOpenChange={(value) => { if (!value && !busy) { setDeletePlan(null); setDeleteRevision(null); } }}>
    <DialogContent className="max-h-[85vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>删除版本 {deleteRevision}</DialogTitle>
        <DialogDescription>确认后立即撤销关联分享并删除专属文件。此操作无法恢复，当前草稿保留。</DialogDescription>
      </DialogHeader>
      {deletePlan && <div className="space-y-3 text-sm">
        <p>{history.find(item => item.revision === deleteRevision)?.name || "未命名版本"} · {history.find(item => item.revision === deleteRevision)?.created_at}</p>
        <p>{status?.savedRevision === deleteRevision ? "这是最新保存版本。" : ""}{deletePlan.clearsPublication ? "删除后清空当前发布状态。" : ""}</p>
        <p>{deletePlan.nextSavedRevision ? `在线只读将使用版本 ${deletePlan.nextSavedRevision}。` : "删除后暂无已保存版本；在线只读不会显示草稿。"}</p>
        <p>将删除 {deletePlan.objects.length} 组专属文件及 {deletePlan.datasets.length} 个无引用数据版本。</p>
        <p>COS 预计删除 {(deletePlan.cosBytes / 1024 / 1024).toFixed(2)} MB；PostgreSQL 内容估算 {(deletePlan.postgresBytes / 1024).toFixed(1)} KB。</p>
        {deletePlan.shares.length > 0 && <div><p>以下分享将整体撤销：</p><ul className="list-disc pl-5">{deletePlan.shares.map((share: Config) =>
          <li key={share.shareId}>{share.url ? <a href={share.url} target="_blank" rel="noreferrer" className="break-all underline">{share.url}</a> : share.shareId} · {share.pages.length} 个页面</li>)}</ul></div>}
        {deletePlan.retained.length > 0 && <div><p>以下数据仍被使用，保留：</p><ul className="list-disc pl-5">{deletePlan.retained.map((item: Config, index: number) =>
          <li key={item.id || item.version || index} className="break-all">{item.version || item.id}：{item.references.map((ref: Config) => `${ref.dashboardId || ""} ${referenceLabel(ref.source)}${ref.revision ? ` ${ref.revision}` : ""}`).join("、")}</li>)}</ul></div>}
        <p className="text-muted-foreground">检查时间：{new Date(deletePlan.checkedAt).toLocaleString()}。数据库内容删除不代表计费空间立即下降。</p>
        {error && <p role="alert" className="text-destructive">{error}</p>}
      </div>}
      <DialogFooter>
        <Button variant="outline" disabled={busy} onClick={() => { setDeletePlan(null); setDeleteRevision(null); }}>取消</Button>
        <Button variant="destructive" disabled={busy} onClick={() => void run(async () => {
          try {
            const result = await call("dashboard_version_delete", {
              dashboardId: document.id, expectedRevision: status?.draftRevision, revision: deleteRevision, confirmation: deletePlan?.token,
            });
            setDeleteResult(result); if (preview?.revision === deleteRevision) setPreview(null);
            setDeletePlan(null); setDeleteRevision(null); await refresh(); await onSaved();
          } catch (failure) {
            if (failure instanceof Error && "code" in failure && failure.code === "PLAN_CHANGED") {
              const current = await call("dashboard_version_status", { dashboardId: document.id });
              setStatus(current);
              setDeletePlan(await call("dashboard_version_delete_preview", {
                dashboardId: document.id, expectedRevision: current.draftRevision, revision: deleteRevision,
              }));
              throw Error("删除影响已变化，已更新清单，请重新确认。");
            }
            throw failure;
          }
        })}>{busy ? "正在删除…" : "确认删除"}</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
  <Dialog open={preview !== null} onOpenChange={(value) => { if (!value) { previewSequence.current++; setPreview(null); } }}>
    <DialogContent className="h-[92vh] max-w-[96vw] overflow-y-auto sm:max-w-[96vw]">
      <DialogHeader><DialogTitle>正在查看版本 {preview?.revision}</DialogTitle>
        <DialogDescription>只读历史内容；筛选不会修改草稿或发布状态。</DialogDescription></DialogHeader>
      {preview && <HistoryPreview key={`${preview.id}:${preview.revision}`} document={preview} remote={call} />}
    </DialogContent>
  </Dialog>
  <Dialog open={feedback !== null} onOpenChange={(value) => { if (!value) setFeedback(null); }}>
    <DialogContent>
      <DialogHeader><DialogTitle>分享反馈 · 版本 {feedback?.revision}</DialogTitle>
        <DialogDescription>批注定位到这个分享的原版本；本机草稿保持原样。</DialogDescription></DialogHeader>
      {feedback && <>
        <p className="text-sm">该分享有 {feedback.annotations?.length ?? 0} 条批注。打开原分享版本，可查看批注并定位到对应组件或段落。</p>
        <div className="flex items-center gap-3">
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void run(() => openFeedback(feedback))}><RefreshCw />重新读取反馈</Button>
          <a href={feedback.feedbackUrl} target="_blank" rel="noreferrer" className="text-sm text-primary underline underline-offset-4">打开版本 {feedback.revision} 的批注</a>
        </div>
      </>}
    </DialogContent>
  </Dialog></>;
}

function referenceLabel(source: string) {
  return ({ draft: "当前草稿", checkpoint: "保存版本", release: "发布版本", annotations: "批注",
    "annotation-history": "批注历史", "local-data": "本地数据资产" } as Record<string, string>)[source] || source;
}

function HistoryPreview({ document, remote }: { document: Document; remote: ToolCall }) {
  const [reader, setReader] = useState<ReturnType<typeof createVersionReader> | null>(null);
  useEffect(() => {
    const boot = window.__chartsBoot || {};
    const tokenKey = `charts-design-token:${boot.apiBase || "/api/tools/"}:${boot.projectRoot || ""}:${boot.dashboardId || ""}`;
    const token = sessionStorage.getItem(tokenKey) || "";
    const browser = createVersionReader(document, (boot.apiBase || "").split("/api/")[0] + "/assets/static-worker.js",
      token ? { Authorization: "Bearer " + token } : {});
    const operations: Record<string, string> = { dashboard_view: "view", dashboard_filter_options: "options",
      component_data: "details", semantic_inspect: "semantic", dataset_export: "export" };
    const value = document.storageFormat === "cos-v1" ? browser : {
      destroy: browser.destroy,
      call: (name: string, request: Config = {}) => operations[name]
        ? remote("dashboard_version_query", { dashboardId: document.id, revision: document.revision, operation: operations[name], request })
        : browser.call(name, request),
    };
    setReader(value);
    return () => value.destroy();
  }, [document, remote]);
  return reader ? <DashboardApp initial={document} call={reader.call} readOnly staticMode /> : <p>正在打开历史版本…</p>;
}
