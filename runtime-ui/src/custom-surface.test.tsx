import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "bun:test";
import { CustomSurface } from "./custom-surface";

afterEach(cleanup);

// @wu-test type=boundary | scope=CustomSurface | protects=自定义脚本获得宿主同源权限或数据文本被执行为脚本
it("隔离作者脚本并将数据作为 JSON 传入", () => {
  render(<CustomSurface title="自定义图表" config={{
    html: "<div id='chart'></div>",
    data: { label: "</script><script>parent.injected=true</script>" },
  }} />);
  const frame = screen.getByTitle("自定义图表") as HTMLIFrameElement;
  expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
  expect(frame.srcdoc).toContain('window.chartData={"label":"\\u003c/script>\\u003cscript>parent.injected=true\\u003c/script>"}');
  expect(frame.srcdoc).toContain("<div id='chart'></div>");
});

// @wu-test type=boundary | scope=CustomSurface错误消息 | protects=其他窗口伪造组件错误或组件真实错误未展示
it("只接受所属 iframe 的运行错误", () => {
  render(<CustomSurface title="自定义图表" config={{ html: "<p>值</p>" }} />);
  const frame = screen.getByTitle("自定义图表") as HTMLIFrameElement;
  act(() => window.dispatchEvent(new MessageEvent("message", {
    source: window, data: { type: "charts:custom-error", message: "伪造错误" },
  })));
  expect(screen.queryByText("伪造错误")).toBeNull();
  act(() => window.dispatchEvent(new MessageEvent("message", {
    source: frame.contentWindow, data: { type: "charts:custom-error", message: "计算失败" },
  })));
  expect(screen.getByText("自定义组件运行失败")).toBeTruthy();
});
