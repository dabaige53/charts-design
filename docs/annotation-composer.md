# 看板位置引用与对话批注

位置批注有两种方式：支持宿主扩展时附到对话；不支持扩展的客户端和独立网页保存页面批注。编辑模式不提供旧版全局、页面或图表批注按钮。查看模式保留位置批注能力，已有批注数据与读取工具继续保留。

## 附到宿主对话

MCP 客户端同时声明 `experimental["openai/modelContext"]` 和 `updateModelContext.text` 时，位置批注提供正文输入框和“提交”按钮。用户选中元素或拖选区域，填写批注后提交，位置和正文附到宿主输入框；用户之后自行发送对话。页面不调用消息发送接口，也不把新引用保存为看板批注。

每个引用包含项目路径、看板 ID、版本、组件 ID、选区、选中文本、筛选条件，以及已有批注的正文。连续附加保留之前的引用。客户端通过 `openai/modelContext` 通知移除时，同步当前附件。已有批注仍可打开并附到对话。

提交成功后关闭输入面板、清除当前选区，并保持批注模式，用户可继续选择下一个位置。提交失败保留正文与选区供重试。Esc 或“退出批注”退出模式。批注期间暂停页面报表自动刷新，避免打断输入；退出后恢复图表交互。独立的界面版本检查只显示更新提示。

`runtime-ui/host-app.mjs` 对 SDK 1.1.2 的初始化结果保留厂商 experimental 字段，保留标准能力校验；只有宿主明确声明能力时才显示“提交”。SDK 依赖版本以 `runtime-ui/package.json` 及锁文件为准。

只有用户确认宿主输入框的附加、编辑、移除、发送流程可用后，才决定是否撤掉其余页面批注管理功能。自动检查不能替代这项宿主验收。

协议定义见 [MCP 扩展规范](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md#uiupdate-model-context-extensions)。

## 页面批注与存储

不支持上述扩展的客户端和独立网页使用页面保存：在查看模式点击“批注”，选择元素或区域，输入并保存，支持 Cmd/Ctrl+Enter。编号标记打开已有批注，列表支持跳转、修改与删除。离线 HTML 只能查看已有批注，不保存修改。批注不提供样式调整。

保存的批注在文档中表示为 `manifest.annotations`，每项包含 `id`、`componentId`（页面批注为 `null`）、`text` 和 `createdAt`。`set_annotations` 整体替换列表，最多 100 条，每条正文最多 4000 字；修改受版本检查约束。

位置字段 `anchor` 可包含：

- `scope`：component、text 或 page。
- `kind`：element 或 area。
- `quote`：最多 1000 字的选中文本。
- `rect`：相对目标的 x、y、width、height，取值 0–1。
- `occurrence`：文字引文重复时，从 0 开始的匹配序号。

报告图表也暴露组件 ID，位置随图表移动与尺寸变化。文字通过引文匹配；引文改变或组件移除后，列表保留内容并显示位置失效。跨组件区域绑定页面相对位置，页面结构变化可能使区域偏移。引文和坐标不是截图，定位不明确时需检查实际页面。

项目模式的批注独立保存，不随设计恢复回退；旧集中存储沿用其历史版本行为。JSON 导出保留已有批注。修改看板时保留原批注，除非用户明确要求修改或删除。

## Agent 读取并处理批注

用户在对话中要求读取或按批注修改时，调用 `dashboard_annotations`，每次传入 `projectRoot` 和 `dashboardId`。结果包含当前版本、原始批注与锚点，以及按批注 ID 索引的目标标题、类型和配置位置；不读取图表明细或生成图表。组件已删除时返回 `componentExists: false`。`dashboard_get` 摘要的 `annotationCount` 可用于发现已有批注。

根据批注 ID 和 componentId 定位，读取当前文档后，按共享交付流程开始编辑批次、使用最新 `expectedRevision` 修改、完成检查，再预览一次。附到对话的引用由用户发送后处理；保存页面批注本身不会自动触发 Agent。

## 页面生命周期与检查

页面由宿主创建和销毁，收到 `ui/resource-teardown` 时释放刷新、保活和观察器。服务连接及工作进程独立于页面，关闭一个页面不终止其他会话的进程。看板使用同版本的 UI 资源，URI 含构建标识；是否复用页面由宿主决定，项目不承诺跨工具调用的页面单例。

`runtime_info` 提供进程、项目、运行目录和前后端构建标识；“运行诊断”显示页面与服务版本及实际批注模式。安装更新和重连步骤统一见 [本地 MCP 更新](local-mcp-update.md)。

```sh
node --test tests/runtime/annotation-context.test.mjs tests/runtime/annotations.test.mjs tests/runtime/host-app.test.mjs tests/runtime/lifecycle.test.mjs
npm --prefix runtime-ui run build
```

回归检查通过真实 SDK schema 检查能力字段，不只模拟能力对象。实际宿主仍需检查附加、连续引用、编辑、移除与发送流程。维护时机：宿主扩展、批注字段、保存方式或页面生命周期变化时更新本文。
