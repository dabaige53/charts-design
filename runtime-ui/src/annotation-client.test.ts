import { afterEach, expect, it, mock } from "bun:test";
import { createAnnotationClient } from "./annotation-client";
import type { AnnotationAccess } from "./types";

const originalFetch = globalThis.fetch;
const originalLocation = Object.getOwnPropertyDescriptor(globalThis, "location");
afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalLocation) Object.defineProperty(globalThis, "location", originalLocation);
  else Reflect.deleteProperty(globalThis, "location");
});
const access: AnnotationAccess = { endpoint: "/s/first/api/annotations", canRead: true,
  canAnnotate: true, canManageAnnotations: false, scope: "share:first" };
function setLocation() {
  Object.defineProperty(globalThis, "location", { configurable: true, value: new URL("https://charts.example/s/first/") });
}

// @wu-test type=integration | scope=批注HTTP传输 | protects=批注误走MCP或整页更新、网络失败被当作成功、重试丢失原ID和版本
it("pins an append to the displayed version and retries its original identity after failure", async () => {
  setLocation();
  let attempts = 0;
  const fetchMock = mock(async (_url: RequestInfo | URL, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body));
    return ++attempts === 1
      ? Response.json({ error: { message: "存储暂不可用" } }, { status: 503 })
      : Response.json({ annotation: { ...body.append, author: { name: body.authorName, verified: false } }, revision: 4 });
  });
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  const call = createAnnotationClient(access, () => 4);
  const note = { id: "stable-note", text: "保留此处", authorName: "小林", view: { revision: 4 } };
  await expect(call("dashboard_annotations_update", { dashboardId: "board", append: note })).rejects.toThrow("存储暂不可用");
  const saved = await call("dashboard_annotations_update", { dashboardId: "board", append: note });
  expect(saved.annotation.id).toBe("stable-note");
  expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual(Array(2).fill("https://charts.example/s/first/api/annotations"));
  expect(fetchMock.mock.calls[0][1]?.body).toBe(fetchMock.mock.calls[1][1]?.body);
  expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({
    dashboardId: "board", revision: 4, authorName: "小林",
    append: { id: "stable-note", text: "保留此处", view: { revision: 4 } },
  });
  expect(note.authorName).toBe("小林");
});

// @wu-test type=security | scope=批注客户端权限 | protects=仅查看链接发起写入、读者替换其他批注、内容工具误用批注服务
it("does not dispatch content writes or annotation management from a reader capability", async () => {
  setLocation();
  const fetchMock = mock(async () => Response.json({}));
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  const reader = createAnnotationClient({ ...access, canAnnotate: false }, () => 4);
  await expect(reader("dashboard_annotations_update", { dashboardId: "board", append: {} })).rejects.toThrow("权限");
  const commenter = createAnnotationClient(access, () => 4);
  await expect(commenter("dashboard_annotations_update", { dashboardId: "board", annotations: [] })).rejects.toThrow("仅允许新增");
  await expect(commenter("dashboard_patch", { dashboardId: "board" })).rejects.toThrow("仅支持批注");
  expect(fetchMock).not.toHaveBeenCalled();
});

// @wu-test type=security | scope=批注HTTP地址 | protects=分享文档诱导浏览器将作者token发送到外站
it("reads only the configured same-origin scope and never forwards author credentials elsewhere", async () => {
  setLocation();
  const fetchMock = mock(async (_url: RequestInfo | URL, _init?: RequestInit) => Response.json({ revision: 4, annotations: [], canAnnotate: true }));
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  const headers = () => ({ Authorization: "Bearer workspace-token" });
  const foreign = createAnnotationClient({ ...access, endpoint: "https://untrusted.example/annotations" }, () => 4, headers);
  await expect(foreign("dashboard_annotations", { dashboardId: "board" })).rejects.toThrow("同源");
  expect(fetchMock).not.toHaveBeenCalled();
  const local = createAnnotationClient({ ...access, endpoint: "/api/annotations/{dashboardId}" }, () => 4, headers);
  await local("dashboard_annotations", { dashboardId: "board" });
  const [url, init] = fetchMock.mock.calls[0];
  expect(String(url)).toBe("https://charts.example/api/annotations/board?dashboardId=board&revision=4");
  expect(init).toMatchObject({ cache: "no-store", credentials: "same-origin", headers: { Authorization: "Bearer workspace-token" } });
});
