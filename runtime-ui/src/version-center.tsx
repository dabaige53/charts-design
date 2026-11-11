import React, { useCallback, useEffect, useState } from "react";
import { Check, Eye, RotateCcw, Save, Send } from "lucide-react";
import { Button } from "./ui";
import { Input } from "./components/ui/input";
import { Badge } from "./components/ui/badge";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "./components/ui/sheet";
import type { Config, Document, ToolCall } from "./types";

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
    setHistory(saved.history);
  }, [call, document.id]);
  useEffect(() => {
    if (!open) return;
    setError(""); setPreview(null); setNewShare(null);
    void refresh().catch((e) => setError(String(e.message || e)));
  }, [open, refresh]);
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
  return <Sheet open={open} onOpenChange={onOpenChange}>
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
                {status?.publishedRevision === item.revision && <Badge><Check />当前发布</Badge>}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">版本 {item.revision} · {item.created_at}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" variant="outline" disabled={busy} onClick={() => void run(async () => {
                  const result = await call("dashboard_version_get", { dashboardId: document.id, revision: item.revision });
                  setPreview(result.version);
                })}><Eye />查看内容</Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => void run(async () => {
                  await onRestore(item.revision); await refresh(); setPreview(null);
                })}><RotateCcw />恢复为草稿</Button>
                <Button size="sm" disabled={busy || status?.publishedRevision === item.revision} onClick={() => void run(async () => {
                  await call("dashboard_version_publish", { dashboardId: document.id, expectedRevision: status?.draftRevision, revision: item.revision });
                  await refresh();
                })}><Send />发布此版本</Button>
              </div>
            </article>)}
          </div>
          {preview && <section className="rounded-lg border bg-muted/30 p-3" aria-label="历史版本内容">
            <h3 className="font-medium">版本 {preview.revision} · {preview.manifest.title}</h3>
            <p className="mt-1 text-xs text-muted-foreground">只读内容摘要 · {Object.keys(preview.manifest.components).length} 个组件 · {Object.keys(preview.manifest.datasets).length} 个数据集</p>
            <ul className="mt-3 space-y-1">
              {Object.entries(preview.manifest.components).map(([id, component]) =>
                <li key={id}>{component.title || component.config?.title || id}</li>)}
            </ul>
          </section>}
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
  </Sheet>;
}
