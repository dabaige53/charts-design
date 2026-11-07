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

## 未验证与已知问题

- 未构建 Docker 镜像，未经 nginx 代理实测，未连接 claude.ai、Claude Desktop 或 Codex 等真实宿主；宿主验收仍待进行。
- `tests/runtime/test_browser.py::test_display_preserves_chart_switch_and_service_updates` 在改动前已失败：测试等待编辑模式中的“图表批注”按钮，而现行批注规范已移除该按钮。本次未修改该测试。
- 本机系统级 mcp 为 2.3，与项目要求的 `<2` 不符；测试通过 `.charts-runtime-env.json` 指向 `.mcp-test-deps` 中的 1.30 运行。
