import { Alert, AlertDescription, AlertTitle } from "./components/ui/alert";
import { Button } from "./ui";

export function RecoveryAlert({
  title,
  message,
  onRetry,
  retryLabel = "重新加载",
  busy = false,
  className,
}: {
  title: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  busy?: boolean;
  className?: string;
}) {
  return (
    <Alert variant="destructive" className={className}>
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="gap-3">
        <p>请重试。若问题持续，可展开技术详情查看原因。</p>
        {onRetry && (
          <Button variant="outline" size="sm" disabled={busy} onClick={onRetry}>
            {busy ? "正在加载…" : retryLabel}
          </Button>
        )}
        <details className="w-full">
          <summary className="cursor-pointer text-xs">技术详情</summary>
          <p className="mt-2 whitespace-pre-wrap break-words text-xs">{message}</p>
        </details>
      </AlertDescription>
    </Alert>
  );
}
