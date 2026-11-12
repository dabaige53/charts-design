import React, { useCallback, useEffect, useRef, useState } from "react";
import { Check, Eye, RotateCcw, Save, Send, Trash2 } from "lucide-react";
import { Button } from "./ui";
import { Input } from "./components/ui/input";
import { Badge } from "./components/ui/badge";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "./components/ui/sheet";
import type { Config, Document, ToolCall } from "./types";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "./components/ui/dialog";
import { DashboardApp } from "./dashboard";
import { createVersionReader } from "./cos-client";

export function VersionCenter({ open, onOpenChange, document, call, onRestore, onSaved }: {
  open: boolean; onOpenChange: (open: boolean) => void; document: Document;
  call: ToolCall; onRestore: (revision: number) => Promise<void>; onSaved: () => Promise<void>;
}) {
  const [status, setStatus] = useState<Config | null>(null);
  const [history, setHistory] = useState<Config[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<Document | null>(null);
  const [deleteRevision, setDeleteRevision] = useState<number | null>(null);
  const [deletePlan, setDeletePlan] = useState<Config | null>(null);
  const [deleteResult, setDeleteResult] = useState<Config | null>(null);
  const previewSequence = useRef(0);
  const [tab, setTab] = useState<"versions" | "shares">("versions");
  const [availablePages, setAvailablePages] = useState<Config[]>([]);
  const [selectedPages, setSelectedPages] = useState<string[]>([]);
  const [shares, setShares] = useState<Config[]>([]);
  const [expiration, setExpiration] = useState("7d");
  const [newShare, setNewShare] = useState<Config | null>(null);
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
  const run = async (work: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await work(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  const loadShares = async () => {
    const result = await call("dashboard_share_status", { dashboardId: document.id });
    setShares(result.shares);
    const list = await call("dashboard_list");
    setAvailablePages(list.dashboards.filter((page: Config) => page.id !== document.id));
  };
  return <><Sheet open={open} onOpenChange={onOpenChange}>
    <SheetContent className="overflow-y-auto sm:max-w-xl">
      <SheetHeader>
        <SheetTitle>版本与分享</SheetTitle>
        <SheetDescription>保存编辑成果，选择正式发布版本，再创建独立分享。</SheetDescription>
      </SheetHeader>
      <div className="flex flex-col gap-5 px-4 pb-6">
        <div className="flex gap-2" role="tablist" aria-label="版本与分享">
          <Button role="tab" aria-selected={tab === "versions"} variant={tab === "versions" ? "default" : "outline"}
            onClick={() => setTab("versions")}>版本</Button>
          <Button role="tab" aria-selected={tab === "shares"} variant={tab === "shares" ? "default" : "outline"}
            disabled={busy} onClick={() => { setTab("shares"); void run(loadShares); }}>分享</Button>
        </div>
        {error && <p role="alert" className="text-destructive">{error}</p>}
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
                <Button size="sm" disabled={busy || status?.publishedRevision === item.revision} onClick={() => void run(async () => {
                  await call("dashboard_version_publish", { dashboardId: document.id, expectedRevision: status?.draftRevision, revision: item.revision });
                  await refresh();
                })}><Send />发布此版本</Button>
                <Button size="sm" variant="outline" className="text-destructive hover:text-destructive"
                  disabled={busy}
                  onClick={() => void run(async () => {
                    const current = await call("dashboard_version_status", { dashboardId: document.id });
                    setStatus(current);
                    const plan = await call("dashboard_version_delete_preview", {
                      dashboardId: document.id, expectedRevision: current.draftRevision, revision: item.revision,
                    });
                    setDeleteRevision(item.revision); setDeletePlan(plan); setDeleteResult(null);
                  })}><Trash2 />删除版本</Button>
              </div>
            </article>)}
          </div>
          {!!status?.releases?.length && <section>
            <h3 className="mb-2 font-medium">发布记录</h3>
            <ul className="space-y-2 text-sm text-muted-foreground">{status.releases.map((event: Config) =>
              <li key={event.id}>版本 {event.revision} · {event.created_at}</li>)}</ul>
          </section>}
        </> : <>
          <p className="text-sm text-muted-foreground">新分享固定使用当前发布版本。替换分享会生成新链接和新密钥，旧链接与旧会话失效；其他分享保持原样。</p>
          {availablePages.length > 0 && <fieldset className="space-y-2">
            <legend className="font-medium">分享页面</legend>
            <p className="text-sm text-muted-foreground">当前页面已包含；其他页面需先发布。</p>
            {availablePages.map((page) => <label key={page.id} className="flex items-center gap-2">
              <input type="checkbox" checked={selectedPages.includes(page.id)} onChange={(event) => setSelectedPages(event.target.checked ? [...selectedPages, page.id] : selectedPages.filter((id) => id !== page.id))} />
              {page.title || page.id}
            </label>)}
          </fieldset>}
          <div className="flex gap-2">
            <select aria-label="分享有效期" className="rounded-md border bg-background px-3" value={expiration} onChange={(e) => setExpiration(e.target.value)}>
              <option value="7d">7 天过期</option><option value="30d">30 天过期</option><option value="never">不过期</option>
            </select>
            <Button disabled={busy || !status?.publishedRevision} onClick={() => void run(async () => {
              const pages = await Promise.all(selectedPages.map(async (dashboardId) => {
                const pageStatus = await call("dashboard_version_status", { dashboardId });
                if (!pageStatus.publishedRevision) throw new Error(`请先发布页面：${availablePages.find((page) => page.id === dashboardId)?.title || dashboardId}`);
                return { dashboardId, expectedRevision: pageStatus.publishedRevision };
              }));
              setNewShare(await call("dashboard_share_publish", { dashboardId: document.id, expectedRevision: status?.publishedRevision, expiration, pages }));
              await loadShares();
            })}>新建分享</Button>
          </div>
          {newShare && <div className="rounded-lg border p-3">
            <a className="break-all text-primary underline underline-offset-4" href={newShare.accessUrl || newShare.url}
              target="_blank" rel="noreferrer">{newShare.accessUrl || newShare.url}</a>
            <p className="mt-2">访问密钥：<strong>{newShare.accessKey}</strong></p>
            <p className="mt-1 text-xs text-muted-foreground">请保存密钥；关闭后无法再次查看。</p>
          </div>}
          {shares.map((share) => <article key={share.shareId} className="rounded-lg border p-3">
            <p>{share.pages?.length > 1 ? `包含 ${share.pages.length} 个页面 · ` : ""}版本 {share.revision} · {share.expiresAt ? new Date(share.expiresAt * 1000).toLocaleString() : "不过期"}</p>
            <p className="my-2 text-xs text-muted-foreground">{share.cleanupState === "pending" ? "等待云端清理" : share.state === "active" ? "可访问" : share.state}</p>
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
