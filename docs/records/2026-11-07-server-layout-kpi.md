# 2026-11-07 自托管服务器、构图与指标卡验收记录

对象：分支 `claude/serene-faraday-656fny` 上的自托管服务器（远程 MCP 与网页预览）、布局模板、mc10–mc16 指标卡、图表宽度自适应、`chart_recommend` 与性能改动。环境：Linux 容器，Python 3.13、Node 22、mcp 1.30（`.mcp-test-deps`）、Chromium 153 无头模式。数据均为仓库内合成数据。

## 性能对比

同一合成看板（executive 案例）先生成 100 个检查点，再在同一机器上交替运行基线（提交 `770d4cf` 的工作树）与改动后代码，各取 15 次调用中位数（毫秒）：

| 调用 | 基线第 1 次 / 第 2 次 | 改动后第 1 次 / 第 2 次 |
| --- | --- | --- |
| `dashboard_patch`（改标题） | 90.50 / 95.37 | 7.60 / 8.02 |
| `dashboard_view` 完整 | 6.47 / 5.40 | 3.22 / 3.38 |
| `dashboard_view` 局部（2 个组件） | 3.90 / 3.85 | 2.17 / 2.28 |
| 预览结果打包（10.6 KB） | 1.99 / 1.46 | 0.11 / 0.14 |

原因：每次草稿修改都会重写全部检查点镜像（100 个检查点时约占补丁耗时 85%），现改为只写新增检查点；诊断日志由每条新建连接并提交改为长连接 WAL，Doctor 一次运行合并为一个事务；MCP 结果只序列化一次，同时用于体积判断与文本回退。冷启动导入 mcp SDK 约 0.4 秒未改动；服务器模式为常驻进程，不受空闲退出影响。

## 验证范围

- 自动测试：新增 `test_server.py`、`test_layouts.py`、`test_kpi_cards.py`、`test_recommend.py`、`adaptive.test.mjs`，并更新全组件、声明与生成案例测试。按 CI 顺序的最终结果：前端构建（40 种图表、16 种指标卡）与 `npm run check` 通过；`tests/runtime` 391 通过、1 失败（见下文已知问题，改动前即失败）；`node --test tests/runtime/*.test.mjs` 93 通过；`tests`（不含 runtime）91 通过。
- 浏览器：通过服务器分享链接在 Chromium 中打开看板、报告、编辑页与手机宽度页面，均无脚本或 CSP 错误、无横向溢出；伪造令牌显示失效提示。全组件测试逐个渲染 40 种图表与 16 种指标卡。
- 修复：项目模式下报告图表一直停留在“等待加载…”（渐进加载按组件 ID 查找报告图表，而报告图表按“组件:序号”保存）；本地 `serve` 与服务器预览均受影响，现已修复并有浏览器测试覆盖。

## CI 与测试流程（同日追加）

- `main` 上最近三次 CI 均在前端依赖审计处失败（dompurify 3.4.16 严重、markdown-it 14.3.2 高危及 5 个传递依赖），构建与测试步骤从未执行。升级后审计为 0，GitHub 运行器上 390 通过、2 失败，失败项见下。
- 工作流拆为静态检查、依赖审计、快速测试（Python 3.10 与 3.13）、Chromium 验收、部署镜像五个并行作业，层次与命令见 [测试与 CI](../testing.md)。
- Python 3.10 首次纳入检查后发现并修复：SQLite 多语句在 3.11 以下抛出 `sqlite3.Warning`（不是 `sqlite3.Error`），未被转换为 `QUERY_REJECTED`；`bin/update_local_mcp.py` 依赖 3.11 的 `tomllib`，现给出明确提示，其测试在 3.10 上带原因跳过。
- 部署镜像：本沙箱的出口策略拒绝 Debian 软件源，无法在本地执行前端构建阶段的 `apt-get`；以 `deploy/Dockerfile` 的运行阶段（注入沙箱证书、使用本地已构建前端）构建镜像，`tests/deploy/container_smoke.py --image` 全部通过，容器以 uid 10001 运行。完整多阶段构建由 CI 的部署镜像作业执行。

## 未验证与已知问题

- 未经 nginx 代理实测，未连接 claude.ai、Claude Desktop 或 Codex 等真实宿主；宿主验收仍待进行。
- `tests/runtime/test_browser.py::test_display_preserves_chart_switch_and_service_updates` 在改动前已失败：测试仍点击编辑模式中的“图表批注”按钮，而现行批注规范已移除该按钮。已按文档改为查看模式的“批注”流程，保留创建、修改、重载后在指标说明中显示及删除的检查。
- `tests/runtime/test_annotations_browser.py` 把截图写到 macOS 路径 `/private/tmp`，在 Linux 运行器上无权限创建；改为写入 `component-review/` 并作为 CI 产物上传。
- 本机系统级 mcp 为 2.3，与项目要求的 `<2` 不符；测试通过 `.charts-runtime-env.json` 指向 `.mcp-test-deps` 中的 1.30 运行。
