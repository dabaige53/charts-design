import { Component, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { Toaster } from "sonner";
import { RecoveryAlert } from "./recovery-alert";
import { TooltipProvider } from "./components/ui/tooltip";

class RenderBoundary extends Component<{ children: ReactNode }, { error: string }> {
  state = { error: "" };
  static getDerivedStateFromError(error: Error) {
    return { error: error.message || String(error) };
  }
  render() {
    if (this.state.error)
      return <RecoveryAlert className="m-6" title="页面暂时无法显示"
        message={this.state.error} retryLabel="重新打开页面" onRetry={() => location.reload()} />;
    return this.props.children;
  }
}

export function mountApp(children: ReactNode) {
  window.__chartsReady = async () => {
    await document.fonts.ready;
    await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  };
  createRoot(document.getElementById("root")!).render(
    <RenderBoundary><TooltipProvider>{children}<Toaster closeButton /></TooltipProvider></RenderBoundary>,
  );
}
