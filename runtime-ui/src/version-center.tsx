import React, { useCallback, useEffect, useRef, useState } from "react";
import { Check, ChevronDown, ChevronRight, Copy, Eye, Pencil, RotateCcw, Trash2 } from "lucide-react";
import { Button } from "./ui";
import { Input } from "./components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "./components/ui/sheet";
import type { Config, Document, ToolCall } from "./types";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "./components/ui/dialog";
import { DashboardApp } from "./dashboard";
import { createVersionReader } from "./cos-client";

type SharePlan = { share: Config; pages: { id: string; title: string; from: number; to: number }[] };

export function VersionCenter({ open, onOpenChange, document, call, onRestore, onSaved }: {
  open: boolean; onOpenChange: (open: boolean) => void; document: Document;
  call: ToolCall; onRestore: (revision: number) => Promise<void>; onSaved: () => Promise<void>;
}) {
  const [status, setStatus] = useState<Config | null>(null);
  const [history, setHistory] = useState<Config[]>([]);
  const [busy, setBusy] = useState(false), [pendingAction, setPendingAction] = useState("");
  const [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [conflict, setConflict] = useState(false);
  const [editingName, setEditingName] = useState<number | null>(null), [name, setName] = useState("");
  const [restore, setRestore] = useState<Config | null>(null);
  const [preview, setPreview] = useState<Document | null>(null);
  const [deleteRevision, setDeleteRevision] = useState<number | null>(null);
  const [deletePlan, setDeletePlan] = useState<Config | null>(null);
  const [deleteResult, setDeleteResult] = useState<Config | null>(null);
  const previewSequence = useRef(0);
  const [tab, setTab] = useState<"versions" | "shares">("versions");
  const [availablePages, setAvailablePages] = useState<Config[]>([]), [selectedPages, setSelectedPages] = useState<string[]>([]);
  const [shares, setShares] = useState<Config[]>([]), [selectedShares, setSelectedShares] = useState<string[]>([]);
  const [expandedShares, setExpandedShares] = useState<string[]>([]);
  const [expiration, setExpiration] = useState("7d"), [creating, setCreating] = useState(false);
  const [plans, setPlans] = useState<SharePlan[] | null>(null), [revoke, setRevoke] = useState<Config | null>(null);
  const [createdShares, setCreatedShares] = useState<Config[]>([]), [copied, setCopied] = useState("");
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
    setError(""); setNotice(""); setConflict(false); setPreview(null); setDeleteRevision(null); setDeletePlan(null);
    setPlans(null); setRestore(null); setRevoke(null); setCreating(false); setCreatedShares([]); setSelectedShares([]);
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
    setBusy(true); setError(""); setNotice(""); setPendingAction(message);
    try { await work(); } catch (e) {
      if ((e instanceof Error && "code" in e && e.code === "REVISION_CONFLICT") || String(e).includes("REVISION_CONFLICT")) {
        setConflict(true); setPlans(null); setDeletePlan(null); setDeleteRevision(null); setRestore(null);
        setError("内容已在别处更新。请先加载最新内容，检查后再操作。");
      } else if (e instanceof Error && "code" in e && e.code === "DOCTOR_FAILED") {
        setError("草稿检查未通过，版本未保存。请让 Agent 检查并修复草稿后重试。");
      } else setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); setPendingAction(""); }
  };
  const loadShares = async () => {
    const [result, list] = await Promise.all([
      call("dashboard_share_status", { dashboardId: document.id }), call("dashboard_list"),
    ]);
    const pageVersions = await Promise.all(list.dashboards.filter((page: Config) => page.id !== document.id).map(async (page: Config) => {
      const pageStatus = await call("dashboard_version_status", { dashboardId: page.id });
      return { ...page, savedRevision: pageStatus.savedRevision };
    }));
    setShares(result.shares); setAvailablePages(pageVersions);
    setSelectedPages((selected) => selected.filter((id) => pageVersions.some((page: Config) => page.id === id && page.savedRevision)));
    setSelectedShares((selected) => selected.filter((id) => result.shares.some((share: Config) => share.shareId === id && share.state === "active")));
  };
  const pageTitle = (id: string) => id === document.id ? document.manifest.title : availablePages.find(page => page.id === id)?.title || id;
  const sharePages = (share: Config) => share.pages?.length ? share.pages : [{ id: document.id, revision: share.revision }];
  const makePlans = async (selected: Config[]) => {
    const ids = [...new Set(selected.flatMap(share => sharePages(share).map((page: Config) => page.id)))];
    const values = await Promise.all(ids.map(async (id) => [id, (await call("dashboard_version_status", { dashboardId: id })).savedRevision] as const));
    const revisions = new Map(values);
    const next = selected.map(share => ({ share, pages: sharePages(share).map((page: Config) => {
      const revision = revisions.get(page.id);
      if (!revision) throw Error(`页面“${pageTitle(page.id)}”没有已保存版本。`);
      return { id: page.id, title: page.title || pageTitle(page.id), from: page.revision, to: revision as number };
    }) }));
    setPlans(next);
  };
  const copy = async (value: string, key: string) => {
    try { await navigator.clipboard.writeText(value); setCopied(key); }
    catch { setError("复制失败，请手动选择并复制。"); }
  };
  const activeShares = shares.filter(share => share.state === "active");
  const latestByPage = new Map<string, number | null>([[document.id, status?.savedRevision], ...availablePages.map(page => [page.id, page.savedRevision] as [string, number | null])]);
  const versionName = (item: Config) => item.name || `版本 ${item.revision}`;
  return <><Sheet open={open} onOpenChange={(value) => { if (!busy) onOpenChange(value); }}>
    <SheetContent className="overflow-y-auto sm:max-w-xl">
      <SheetHeader><SheetTitle>版本与分享</SheetTitle><SheetDescription>管理页面版本与分享链接</SheetDescription></SheetHeader>
      <div className="flex flex-col gap-5 px-4 pb-6">
        <div className="flex gap-5 border-b" role="tablist" aria-label="版本与分享">
          {([['versions', '页面版本'], ['shares', '分享链接']] as const).map(([value, label]) => <button key={value} role="tab" aria-selected={tab === value}
            className={`border-b-2 pb-2 text-sm ${tab === value ? 'border-primary font-medium text-primary' : 'border-transparent text-muted-foreground'}`}
            disabled={busy} onClick={() => { setTab(value); setError(""); setNotice(""); if (value === "shares") void run(loadShares); }}>{label}</button>)}
        </div>
        {error && <p role="alert" className="text-destructive">{error}</p>}
        {conflict && <Button variant="outline" disabled={busy} onClick={() => void run(async () => {
          await onSaved(); await refresh(); if (tab === "shares") await loadShares(); setConflict(false); setNotice("已加载最新内容，请检查后重新操作。");
        }, "正在加载最新内容…")}>加载最新内容</Button>}
        {notice && <p role="status">{notice}</p>}{pendingAction && <p role="status">{pendingAction}</p>}
        {deleteResult?.state === "complete" && <p role="status">版本已删除。</p>}
        {(status?.deletionJobs || []).map((job: Config) => <div key={job.id} role="status" className="border p-3">
          <p>版本 {job.revision} · {job.state === "failed" ? "访问已撤销，文件清理未完成" : "正在删除文件"}</p>
          {job.error && <p className="text-sm text-destructive">{job.error}</p>}
          <Button variant="outline" disabled={busy} onClick={() => void run(async () => {
            setDeleteResult(await call("dashboard_version_delete_retry", { dashboardId: document.id, jobId: job.id })); await refresh();
          })}>继续清理</Button></div>)}
        {tab === "versions" ? <>
          <div><p className="text-xs text-muted-foreground">当前页面</p><h3 className="mt-1 font-semibold">{document.manifest.title}</h3></div>
          <section className="space-y-3 border p-4">
            <div><h3 className="font-medium">{!status ? "正在读取保存状态…" : status.draftRevision !== status.savedRevision ? "当前内容有更改" : "当前内容已保存"}</h3>
              <p className="mt-1 text-xs text-muted-foreground">{status?.savedRevision ? `最新保存：版本 ${status.savedRevision}` : "暂无已保存版本"}</p></div>
            <div className="flex flex-wrap items-center gap-3"><Button disabled={busy || !status || conflict || status.draftRevision === status.savedRevision}
              onClick={() => void run(async () => {
                const result = await call("dashboard_checkpoint", { dashboardId: document.id, expectedRevision: status?.draftRevision });
                if (!result.ok) throw Error("保存未完成，请检查草稿后重试。");
                await refresh(); await onSaved(); setNotice(`版本 ${result.checkpoint.revision} 已保存。`);
              }, "正在保存版本…")}>保存当前内容</Button>
              <span className="text-xs text-muted-foreground">{status?.draftRevision === status?.savedRevision ? "页面更改后，可在这里保存新版本。" : "保存后，在线只读页面会显示新版本。"}</span></div>
          </section>
          <section><div className="mb-3 flex items-end justify-between"><div><h3 className="font-medium">历史版本</h3><p className="mt-1 text-xs text-muted-foreground">查看、命名或恢复这个页面的已保存内容。</p></div><span className="text-xs text-muted-foreground">{history.length} 个版本</span></div>
            {history.map(item => <article key={item.revision} className="space-y-2 border-t py-3">
              <div className="flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2"><strong>{versionName(item)}</strong>{status?.savedRevision === item.revision && <span className="bg-muted px-1.5 py-0.5 text-xs">最新保存</span>}</div><span className="text-xs text-muted-foreground">{formatDate(item.created_at)}</span></div>
              {item.name && <p className="text-xs text-muted-foreground">版本 {item.revision}</p>}
              {editingName === item.revision ? <form className="space-y-2 bg-muted p-3" onSubmit={(event) => { event.preventDefault(); void run(async () => {
                if (!name.trim()) throw Error("请输入版本名称。");
                await call("dashboard_version_label", { dashboardId: document.id, expectedRevision: status?.draftRevision, revision: item.revision, name: name.trim(), published: Boolean(item.published) });
                await refresh(); setEditingName(null); setName(""); setNotice(`版本 ${item.revision} 的名称已更新。`);
              }); }}><label htmlFor={`version-name-${item.revision}`} className="text-xs">版本名称</label><div className="flex flex-wrap gap-2"><Input id={`version-name-${item.revision}`} value={name} onChange={e => setName(e.target.value)} className="min-w-32 flex-1" /><Button type="submit" disabled={busy || conflict}>保存名称</Button><Button type="button" variant="ghost" onClick={() => setEditingName(null)}>取消</Button></div></form>
              : <div className="flex flex-wrap gap-1"><Button size="sm" variant="ghost" aria-label="查看版本" disabled={busy} onClick={() => void run(async () => {
                const sequence = ++previewSequence.current; const result = await call("dashboard_version_get", { dashboardId: document.id, revision: item.revision }); if (sequence === previewSequence.current) setPreview(result.version);
              })}><Eye />查看</Button>{item.action !== "release" && <Button size="sm" variant="ghost" aria-label="修改版本名称" disabled={busy} onClick={() => { setEditingName(item.revision); setName(item.name || ""); }}><Pencil />修改名称</Button>}
              <Button size="sm" variant="ghost" aria-label="恢复版本" disabled={busy || conflict} onClick={() => setRestore(item)}><RotateCcw />恢复</Button>
              <Button size="sm" variant="ghost" aria-label="删除版本" className="text-destructive" disabled={busy} onClick={() => void run(async () => {
                const current = await call("dashboard_version_status", { dashboardId: document.id }); setStatus(current);
                const plan = await call("dashboard_version_delete_preview", { dashboardId: document.id, expectedRevision: current.draftRevision, revision: item.revision });
                setDeleteRevision(item.revision); setDeletePlan(plan); setDeleteResult(null);
              }, "正在检查删除影响…")}><Trash2 />删除</Button></div>}
            </article>)}{!history.length && <p className="border-t py-3 text-sm text-muted-foreground">暂无历史版本。</p>}</section>
        </> : <>
          <section className="flex flex-wrap items-center justify-between gap-3 border-b pb-5"><div><h3 className="font-medium">创建分享</h3><p className="mt-1 text-xs text-muted-foreground">选择页面，生成一条新的访问链接。</p></div><Button disabled={busy || !status?.savedRevision} onClick={() => setCreating(true)}>创建分享</Button></section>
          {createdShares.length > 0 && <section className="space-y-3 border p-3"><h3 className="font-medium">已生成新链接</h3><p className="text-xs text-muted-foreground">请复制链接和密钥；关闭后无法再次查看密钥。</p>{createdShares.map(share => <div key={share.shareId} className="space-y-1 border-t pt-2">{share.previousUrl && <p className="break-all text-xs text-muted-foreground">原链接：{share.previousUrl}</p>}<p className="break-all text-xs">{share.url}</p><p className="text-xs">访问密钥：<strong>{share.accessKey}</strong></p><Button size="sm" variant="outline" onClick={() => void copy(`链接：${share.url}\n访问密钥：${share.accessKey}`, `new:${share.shareId}`)}><Copy />{copied === `new:${share.shareId}` ? "已复制" : "复制链接和密钥"}</Button>{share.previousRevoked === false && <p className="text-xs text-destructive">新链接已创建，但旧链接撤销失败。请保存新密钥，再撤销旧链接。</p>}</div>)}</section>}
          <section><div className="mb-3"><h3 className="font-medium">已有分享</h3><p className="mt-1 text-xs text-muted-foreground">{activeShares.length} 条可访问</p></div>
            {activeShares.length > 0 && <div className="flex flex-wrap items-center justify-between gap-2 bg-muted p-3"><label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={selectedShares.length === activeShares.length} onChange={e => setSelectedShares(e.target.checked ? activeShares.map(s => s.shareId) : [])} />全选可访问的分享</label><Button variant="outline" disabled={busy || conflict || !selectedShares.length} onClick={() => void run(() => makePlans(activeShares.filter(s => selectedShares.includes(s.shareId))), "正在检查页面版本…")}>更新到最新版本{selectedShares.length ? `（${selectedShares.length}）` : ""}</Button></div>}
            {shares.map(share => { const pages = sharePages(share), expanded = expandedShares.includes(share.shareId);
              const changes = pages.filter((page: Config) => latestByPage.get(page.id) != null && latestByPage.get(page.id) !== page.revision).length;
              return <article key={share.shareId} className="space-y-2 border-b py-4"><div className="flex items-start gap-2">
                <input type="checkbox" aria-label={`选择分享 ${share.url || share.shareId}`} className="mt-1" checked={selectedShares.includes(share.shareId)} disabled={share.state !== "active" || busy} onChange={e => setSelectedShares(old => e.target.checked ? [...old, share.shareId] : old.filter(id => id !== share.shareId))} />
                <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><strong>{share.state === "active" ? "可访问" : share.state === "expired" ? "已过期" : share.state === "revoked" ? "已撤销" : "准备中"}</strong></div>
                  {share.url && <div className="mt-1 flex flex-wrap items-center gap-2"><span className="break-all text-xs text-muted-foreground">{share.url}</span>{share.state === "active" && <Button variant="ghost" size="xs" onClick={() => void copy(share.url, share.shareId)}><Copy />{copied === share.shareId ? "已复制" : "复制链接"}</Button>}</div>}
                  <p className="mt-2 text-xs text-muted-foreground">{pages.length} 个页面 · {share.expiresAt ? `有效期至 ${formatDate(share.expiresAt * 1000)}` : "不过期"}{share.state === "active" && changes ? ` · ${changes} 个页面与最新保存版本不同` : ""}</p></div>
                <Button variant="ghost" size="icon-sm" aria-label={`${expanded ? '收起' : '展开'}分享 ${share.url || share.shareId}`} onClick={() => setExpandedShares(old => expanded ? old.filter(id => id !== share.shareId) : [...old, share.shareId])}>{expanded ? <ChevronDown /> : <ChevronRight />}</Button>
              </div>{expanded && <div className="ml-6 space-y-2 bg-muted p-3"><div className="flex justify-between text-xs text-muted-foreground"><span>链接中的页面</span><span>创建时的版本</span></div>
                {pages.map((page: Config) => <div key={page.id} className="flex justify-between gap-2 text-xs"><span>{page.title || pageTitle(page.id)}</span><span>版本 {page.revision}{latestByPage.get(page.id) != null && latestByPage.get(page.id) !== page.revision ? ` · 最新保存 ${latestByPage.get(page.id)}` : ""}</span></div>)}
                {share.cleanupState === "pending" && <p className="text-xs text-muted-foreground">此分享已失效，分享副本将自动删除；保存的版本不受影响。</p>}
                {share.state === "active" && <><div className="flex flex-wrap gap-2 pt-2"><Button size="sm" variant="outline" disabled={busy || conflict} onClick={() => void run(() => makePlans([share]), "正在检查页面版本…")}>更新到最新版本</Button><Button size="sm" variant="ghost" disabled={busy} onClick={() => setRevoke(share)}>撤销链接</Button></div><p className="text-xs text-muted-foreground">访问密钥仅在创建或更新时显示。</p></>}
              </div>}</article>})}{!shares.length && <p className="border-t py-3 text-sm text-muted-foreground">还没有分享链接。</p>}</section>

        </>}
      </div>
    </SheetContent>
  </Sheet>
  <Dialog open={creating} onOpenChange={value => { if (!busy) setCreating(value); }}><DialogContent><DialogHeader><DialogTitle>创建分享</DialogTitle><DialogDescription>当前页面已包含。每个页面使用最新保存的版本。</DialogDescription></DialogHeader>
    <div className="space-y-3"><p>{document.manifest.title} · 版本 {status?.savedRevision}</p>{availablePages.map(page => <label key={page.id} className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={!page.savedRevision} checked={selectedPages.includes(page.id)} onChange={e => setSelectedPages(old => e.target.checked ? [...old, page.id] : old.filter(id => id !== page.id))} />{page.title || page.id} · {page.savedRevision ? `版本 ${page.savedRevision}` : "尚未保存"}</label>)}
      <label className="flex items-center gap-2 text-sm">有效期<select className="border bg-background p-2" value={expiration} onChange={e => setExpiration(e.target.value)}><option value="7d">7 天</option><option value="30d">30 天</option><option value="never">不过期</option></select></label>{error && <p role="alert" className="text-destructive">{error}</p>}</div>
    <DialogFooter><Button variant="outline" disabled={busy} onClick={() => setCreating(false)}>取消</Button><Button disabled={busy || conflict} onClick={() => void run(async () => {
      const pages = selectedPages.map(id => ({ dashboardId: id, expectedRevision: availablePages.find(page => page.id === id)?.savedRevision }));
      const result = await call("dashboard_share_publish", { dashboardId: document.id, expectedRevision: status?.savedRevision, versionSource: "saved", expiration, pages });
      setCreatedShares(old => [...old, result]); setCreating(false); await loadShares(); setNotice("分享已创建。");
    }, "正在创建分享…")}>创建分享</Button></DialogFooter></DialogContent></Dialog>
  <Dialog open={plans !== null} onOpenChange={value => { if (!value && !busy) setPlans(null); }}><DialogContent className="max-h-[85vh] overflow-y-auto"><DialogHeader><DialogTitle>更新 {plans?.length} 条分享至最新版本</DialogTitle><DialogDescription>每条链接保留原有页面，使用各页面最新保存的版本。</DialogDescription></DialogHeader>
    <div className="space-y-3 text-sm"><p>更新后原链接和已打开的页面会失效。每条分享都会生成新链接和密钥，需要重新发送。</p>{plans?.map(plan => <div key={plan.share.shareId} className="space-y-1 border-t pt-3"><p className="break-all text-xs">{plan.share.url}</p>{plan.pages.map(page => <p key={page.id} className="flex justify-between gap-2 text-xs"><span>{page.title}</span><span>版本 {page.from}{page.from === page.to ? " · 不变" : ` → 版本 ${page.to}`}</span></p>)}</div>)}
      <label className="flex items-center gap-2">新链接有效期<select className="border bg-background p-2" value={expiration} onChange={e => setExpiration(e.target.value)}><option value="7d">7 天</option><option value="30d">30 天</option><option value="never">不过期</option></select></label>{error && <p role="alert" className="text-destructive">{error}</p>}</div>
    <DialogFooter><Button variant="outline" disabled={busy} onClick={() => setPlans(null)}>取消</Button><Button disabled={busy} onClick={() => void run(async () => {
      const reviewed = plans || []; let completed = 0;
      for (const plan of reviewed) {
        try {
          const main = plan.pages.find(page => page.id === document.id);
          if (!main) throw Error("分享页面信息不完整，请重新检查。");
          const replacement = await call("dashboard_share_replace", { dashboardId: document.id, shareId: plan.share.shareId, expectedRevision: main.to, versionSource: "saved", expiration,
            pages: plan.pages.filter(page => page.id !== document.id).map(page => ({ dashboardId: page.id, expectedRevision: page.to })) });
          setCreatedShares(old => [...old, { ...replacement, previousUrl: plan.share.url }]); completed++;
          if (!replacement.previousRevoked) {
            setPlans(null); await loadShares();
            setError(`已生成 ${completed} 条新链接，其中一条旧链接撤销失败。请保存新密钥，再撤销对应旧链接；后续分享未处理。`);
            return;
          }
        } catch {
          setPlans(null); await loadShares();
          throw Error(`已生成 ${completed} 条新链接。本条更新结果未确认，后续分享未处理。请核对分享列表和旧链接后再操作。`);
        }
      }
      setPlans(null); setSelectedShares([]); await loadShares(); setNotice(`已更新 ${completed} 条分享。请保存新链接和密钥。`);
    }, "正在更新分享…")}>确认更新 {plans?.length} 条分享</Button></DialogFooter></DialogContent></Dialog>
  <Dialog open={revoke !== null} onOpenChange={value => { if (!value && !busy) setRevoke(null); }}><DialogContent><DialogHeader><DialogTitle>撤销分享链接</DialogTitle><DialogDescription>撤销后，这条链接和已打开的页面将无法访问。保存的页面版本保留。</DialogDescription></DialogHeader><p className="break-all text-xs">{revoke?.url}</p>{error && <p role="alert" className="text-destructive">{error}</p>}<DialogFooter><Button variant="outline" disabled={busy} onClick={() => setRevoke(null)}>取消</Button><Button variant="destructive" disabled={busy} onClick={() => void run(async () => { if (!revoke) return; await call("dashboard_share_delete", { dashboardId: document.id, shareId: revoke.shareId }); setRevoke(null); await loadShares(); setNotice("分享已撤销。"); }, "正在撤销分享…")}>撤销链接</Button></DialogFooter></DialogContent></Dialog>
  <Dialog open={restore !== null} onOpenChange={value => { if (!value && !busy) setRestore(null); }}><DialogContent><DialogHeader><DialogTitle>恢复 {restore && versionName(restore)}</DialogTitle><DialogDescription>恢复后当前页面会变为该版本的内容。保存后生成新版本，已有分享保持不变。</DialogDescription></DialogHeader>{status?.draftRevision !== status?.savedRevision && <p className="text-sm">当前内容有尚未保存为版本的更改。需要保留时，请先取消并保存。</p>}{error && <p role="alert" className="text-destructive">{error}</p>}<DialogFooter><Button variant="outline" disabled={busy} onClick={() => setRestore(null)}>取消</Button><Button disabled={busy} onClick={() => void run(async () => { if (!restore) return; await onRestore(restore.revision); await refresh(); setPreview(null); setRestore(null); setNotice(`已恢复版本 ${restore.revision}，请检查后保存。`); }, "正在恢复版本…")}>恢复到当前页面</Button></DialogFooter></DialogContent></Dialog>
  <Dialog open={deletePlan !== null} onOpenChange={value => { if (!value && !busy) { setDeletePlan(null); setDeleteRevision(null); } }}><DialogContent className="max-h-[85vh] overflow-y-auto"><DialogHeader><DialogTitle>删除版本 {deleteRevision}</DialogTitle><DialogDescription>删除后无法恢复。当前草稿保留。</DialogDescription></DialogHeader>
    {deletePlan && <div className="space-y-3 text-sm"><p>{history.find(item => item.revision === deleteRevision)?.name || `版本 ${deleteRevision}`}</p>{deletePlan.clearsPublication && <p>删除后此页面原有的发布状态会清除。</p>}{status?.savedRevision === deleteRevision && <p>{deletePlan.nextSavedRevision ? `在线只读将显示版本 ${deletePlan.nextSavedRevision}。` : "删除后暂无已保存版本，在线只读将无法显示此页面。"}</p>}{deletePlan.shares.length > 0 && <div className="space-y-2"><p>关联的 {deletePlan.shares.length} 条分享将被撤销，包含其他页面的分享也会整体失效。</p><ul className="space-y-1">{deletePlan.shares.map((share: Config) => <li key={share.shareId} className="break-all text-muted-foreground">{share.url || share.shareId}</li>)}</ul></div>}{error && <p role="alert" className="text-destructive">{error}</p>}</div>}
    <DialogFooter><Button variant="outline" disabled={busy} onClick={() => { setDeletePlan(null); setDeleteRevision(null); }}>取消</Button><Button variant="destructive" disabled={busy} onClick={() => void run(async () => {
      try { const result = await call("dashboard_version_delete", { dashboardId: document.id, expectedRevision: status?.draftRevision, revision: deleteRevision, confirmation: deletePlan?.token });
        setDeleteResult(result); if (preview?.revision === deleteRevision) setPreview(null); setDeletePlan(null); setDeleteRevision(null); await refresh(); await onSaved();
      } catch (failure) { if (failure instanceof Error && "code" in failure && failure.code === "PLAN_CHANGED") { const current = await call("dashboard_version_status", { dashboardId: document.id }); setStatus(current); setDeletePlan(await call("dashboard_version_delete_preview", { dashboardId: document.id, expectedRevision: current.draftRevision, revision: deleteRevision })); throw Error("删除影响已变化，已更新清单，请重新确认。"); } throw failure; }
    })}>{busy ? "正在删除…" : "确认删除"}</Button></DialogFooter></DialogContent></Dialog>
  <Dialog open={preview !== null} onOpenChange={value => { if (!value) { previewSequence.current++; setPreview(null); } }}><DialogContent className="h-[92vh] max-w-[96vw] overflow-y-auto sm:max-w-[96vw]"><DialogHeader><DialogTitle>正在查看版本 {preview?.revision}</DialogTitle><DialogDescription>只读历史内容；筛选不会修改当前内容。</DialogDescription></DialogHeader>{preview && <HistoryPreview key={`${preview.id}:${preview.revision}`} document={preview} remote={call} />}</DialogContent></Dialog></>;
}

function formatDate(value: string | number | undefined) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
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
