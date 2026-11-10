# 2026-11-10 共享工作区交付检查

检查对象为 `codex/mcp1110` 当前共享工作区；构建标识 `fb92a52d63cd0bf7`。Python 3.11.13，前端测试使用 Vitest。

## 修复与清理

- 删除示例 KPI 的 `trendLabel`、`gaugeSub`，使示例创建与禁止描述的输入规则一致。
- KPI 编辑和整份文档创建均拒绝描述字段；自由 ECharts、HTML 和未知预设的保存入口使用同一校验。
- 自定义 HTML 使用隔离 iframe；测试覆盖数据注入和错误消息来源。
- 删除废弃 HTML 构建提示分支及对应测试，将资产管理测试命名为 `test_workspace_assets.py`。
- skills 按当前组件、渲染入口、对齐与布局规则整理，修复设计画布文档的相对链接。
- 保留局部筛选、分页、旧响应丢弃、来源图选择状态及分享权限的回归检查。

## 执行结果

| 检查 | 结果 |
| --- | --- |
| Runtime Python 全套及覆盖率 | 573 通过；87.11%，下限 84% |
| 工作区与数据合同 | 38 通过 |
| Node 数据、传输与查询模块 | 69 通过 |
| React 组件与 Runtime 交互 | 9 通过 |
| TypeScript、构建与 Runtime 打包 | 通过 |
| Python ruff、语法、Skill 与文档链接 | 通过 |
| 指定 LSP 复查 | 18 个文件 passed；0 错误 |

运行命令见 [测试与 CI](../testing.md)。Runtime 有两条 Seaborn 调用 Matplotlib `vert` 参数的弃用提示，LSP 有 Tailwind 指令识别警告。

## 交付边界

本机没有 Docker；容器构建与 Python 3.10、3.13 检查由 PR CI 执行。真实 MCP 宿主的下载、剪贴板、全屏和附到对话能力待宿主验收。

百万行 SQLite 性能测量保存在 [性能结果](2026-11-10-polish-performance.json)，对应独立测量副本及其环境。大 JSON 流式导入尚未实现。
