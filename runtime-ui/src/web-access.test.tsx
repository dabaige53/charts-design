import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, mock } from "bun:test";
import { WebAccess } from "./web-access";

afterEach(cleanup);

// @wu-test type=boundary | scope=在线访问链接恢复 | protects=令牌丢失后无法恢复或错误页面的令牌被提交
it("accepts a complete link for this page and rejects a different page", () => {
  const onAccess = mock(() => {});
  render(<WebAccess onAccess={onAccess} />);
  const input = screen.getByLabelText("完整在线访问链接");
  const wrong = new URL("/edit/another/page#token=test-token", window.location.href);
  fireEvent.change(input, { target: { value: wrong.href } });
  fireEvent.click(screen.getByRole("button", { name: "打开看板" }));
  expect(onAccess).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toBeTruthy();
  const link = new URL(window.location.href);
  link.hash = "token=test-token";
  fireEvent.change(input, { target: { value: link.href } });
  fireEvent.click(screen.getByRole("button", { name: "打开看板" }));
  expect(onAccess).toHaveBeenCalledWith("test-token");
  expect((input as HTMLInputElement).value).toBe("");
});
