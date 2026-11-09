# 测试与 CI

检查分为五层，CI 中每层是独立并行的作业：某一层失败时，其他层仍会运行并报告结果。命令以 `package.json` 与 `.github/workflows/dashboard-runtime.yml` 为准。

| 层 | 本地命令 | CI 作业 | 内容 |
| --- | --- | --- | --- |
| 静态检查 | `npm run check`、`npm run lint:py` | Static checks | Node/Python 语法，Skill 入口链接，全部 Markdown 的本地链接与章节锚点（`bin/check-doc-links.js`），ruff 的 pyflakes 规则（未定义名称、未使用导入、无效 f-string） |
| 依赖审计 | `npm --prefix runtime-ui audit --omit=dev --audit-level=moderate` | Dependency audit | 前端生产依赖的已知漏洞；审计失败不会阻止测试作业运行 |
| 快速测试 | `npm run test:unit` | Unit tests（Python 3.10 与 3.13） | `tests/runtime` 中不需要浏览器的测试（模型、服务、MCP stdio、自托管服务器、布局、指标卡、绑定），`node --test` 的浏览器引擎模块，独立生成器测试；覆盖率不低于 84% |
| 浏览器验收 | `npm run test:browser` | Browser acceptance (Chromium) | Playwright 驱动真实 Chromium：全部组件渲染、编辑与拖动、报告、MCP App 宿主、分享预览页、PDF 导出 |
| 部署镜像 | `npm run test:container` | Container image smoke test | 按 `deploy/Dockerfile` 构建镜像并运行，经 HTTP 完成 MCP 初始化、编辑批次建看板、预览页与缓存资源、分享链接权限和签名下载，并确认以非 root 用户运行 |

部署镜像 CI 在构建前放入合成的环境配置文件，运行后检查这些文件、本机工具目录与业务工作区均未进入镜像，并实际导出网页部署包以保护源码白名单的完整性。服务器测试强制多个首次读取同时遇到空运行目录，检查各调用获得同一个完整签名密钥。打印浏览器验收从按钮、Ctrl+P、Cmd+P 和原生打印事件进入，检查屏幕外组件和未准备页面的打印提示；不会只调用准备函数来代替用户入口。

## 浏览器测试的划分

`tests/runtime/conftest.py` 为以下测试自动加上 `browser` 标记：模块名为 `*_browser.py`；测试函数体使用 Playwright；测试函数体请求 PDF 导出（Runtime 用 Chromium 渲染、用 poppler 合并）。快速层用 `-m "not browser"` 运行，不需要浏览器，约 30 秒。新增浏览器测试时沿用上述约定，或在模块名中使用 `_browser` 后缀。

## 本地准备

- Python 依赖：`python3 -m pip install '.[statistics,mcp,test]'`。项目要求 `mcp<2`；若系统已装更新的大版本，安装到 `.mcp-test-deps` 并在 `.charts-runtime-env.json` 中指定，见 [Runtime 说明](dashboard-runtime.md#mcp)。
- 前端：`npm --prefix runtime-ui ci && npm --prefix runtime-ui run build`。多数浏览器测试在未构建时跳过，不计为通过。
- 浏览器：`node bin/python-runtime.js -m playwright install chromium --only-shell`；PDF 测试另需 poppler（`pdfunite`）。
- 静态检查：`python3 -m pip install 'ruff==0.16.9'` 后运行 `npm run lint:py`。
- 容器：需要 Docker（BuildKit）；`tests/deploy/container_smoke.py --url <地址> --token <令牌>` 也可直接检查已经运行的服务器。

## CI 产物与排查

- 每个快速测试作业上传 `unit-reports-py<版本>`：JUnit 报告与 `coverage.xml`；作业摘要列出覆盖率最低的模块。
- 浏览器作业上传 `browser-evidence`：JUnit 报告、`component-review/` 中每个组件的截图与覆盖记录、整页截图。
- 失败时先看对应作业；审计失败只表示依赖需要升级，测试结果仍在其他作业中。

## 修改规则

- 修改测试或 CI 后，本地至少运行受影响的层；改动运行代码时按影响选择测试，历史记录中的通过结果不代表当前源码已验证。
- 不通过跳过、删除或放宽断言让 CI 变绿。行为按文档变更时，同步更新测试与对应文档；仅在明确的版本或环境要求下跳过（如 `bin/update_local_mcp.py` 需要 Python 3.11 的 `tomllib`），并写明原因。
- 覆盖率下限防止回退；提升覆盖后可相应提高 `--cov-fail-under`。
