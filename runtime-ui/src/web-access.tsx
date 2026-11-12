import { useState, type FormEvent } from "react";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";

export function WebAccess({ onAccess }: { onAccess: (token: string) => void }) {
  const [error, setError] = useState("");
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input = event.currentTarget.elements.namedItem("link") as HTMLInputElement;
    let url: URL;
    try {
      url = new URL(input.value.trim());
    } catch {
      setError("请粘贴完整的在线访问链接。");
      return;
    }
    const token = new URLSearchParams(url.hash.slice(1)).get("token");
    if (url.origin !== window.location.origin || url.pathname !== window.location.pathname || !token) {
      setError("链接须与当前页面对应，并包含访问令牌。");
      return;
    }
    input.value = "";
    setError("");
    onAccess(token);
  }
  return <main className="m-6 max-w-xl space-y-4">
    <h1 className="text-lg font-semibold">无法打开看板</h1>
    <p className="text-sm text-muted-foreground">链接可能已过期，或访问令牌在跳转时丢失。请粘贴收到的完整在线访问链接后重试。</p>
    <form onSubmit={submit} className="space-y-3">
      <label htmlFor="web-access-link" className="text-sm font-medium">完整在线访问链接</label>
      <Input id="web-access-link" name="link" type="password" autoComplete="off" required />
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <Button type="submit">打开看板</Button>
    </form>
  </main>;
}
