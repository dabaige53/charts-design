# MCP 大响应与诊断

## 旧版预览

界面更新后，调用工具列表中的固定入口 `dashboard_preview`。工具的 `_meta.ui.resourceUri` 带当前运行版本和 UI 构建标识；不注册 `dashboard_preview_<uiBuildId>` 这样的独立工具名。

过期 UI 资源 URI 返回 `UI_BUILD_EXPIRED`，需要重新调用当前预览。宿主已保存的历史页面不会被服务端直接替换；应使用本次调用生成的新预览。“刷新报表”只更新数据，不替换界面代码。


## 大响应

写入工具默认先生成摘要，再进入以下传输流程；完整文档不会随摘要被缓存为隐藏分块。需要完整写入结果时显式指定 `responseMode=full`，或另读 `dashboard_get`。编辑器在 MCP 调用中显式使用 full。摘要模式与完整结果的字段约定见 [Runtime 编辑与结果确认](../implementation/dashboard-runtime.md#编辑与结果确认)。

超过 48,000 字节的 MCP 工具结果返回 `transport` 描述，不再把完整 JSON 交给宿主转存。描述含 requestId、chunks、bytes 和 base64-json-v1 编码。调用 runtime_result_chunk，按从零开始的 index 读取全部分块，每块最多 24,000 个 ASCII 字符。拼接后 Base64 解码，核对字节数，再按 UTF-8 解码和 JSON 解析。网页客户端自动完成这一流程，代理或自定义消费者也须处理此描述。

结构化结果和纯文本回退路径使用相同的小结果。不得从损坏的 JSON 截取前缀、跳过坏行，或用减少业务行数的方法隐藏传输失败。单次响应保留完整数据语义；本地 transport-results.sqlite3 保存完整响应 24 小时，同一运行目录的进程共享，进程重启不丢失；每次写入清理到期响应。超过 24 小时返回 RESULT_EXPIRED，需重新发起原读取。修改操作不能因响应过期而自动重放。

## 完整配置下载

修改含大型数据快照的组件时，使用正式客户端将完整 `dashboard_get` 结果保存到文件：

```sh
bun run python -- bin/remote-project.py read \
  --project <远程项目名> --dashboard <页面ID> \
  --output /private/tmp/dashboard-current.json
```

连接由 `CHARTS_MCP_URL` 和 `CHARTS_SERVER_TOKENS` 环境变量提供。客户端自动读取全部响应分块，检查请求编号、索引、编码和总字节数；失败时不保存本次结果。完整配置位于输出 JSON 的 `document` 中，终端只输出文件位置、修订号和组件 ID。文件仅当前用户可读写。

自定义消费者复用 `dashboard_runtime.remote_client.call_tool`；上传和页面读取使用同一解析逻辑。读取结果过期时重新执行 read。修改仍通过正常的编辑批次和最新修订号提交，完整下载不自动修改页面。

## 查询日志

- `runtime_diagnostics({limit:30})`：最近记录。
- `runtime_diagnostics({requestId:"报错中的请求编号",limit:100})`：定位同一响应的序列化字节数、分块、首块和末块读取及客户端失败。
- `runtime_report_error`：App 专用，客户端上报解码、渲染失败或完成时序事件，不上传原始响应或业务字段；Agent 通过诊断工具读取结果，不代替客户端生成事件。

日志存于运行目录 transport-diagnostics.sqlite3，保留最近 2,000 条。记录时间、请求编号、工具、阶段、错误码及响应字节数，不记录工具参数、业务记录和凭据。旧页面在本次功能安装前发生的错误无法补写到日志。服务端日志不能单独证明 Codex 宿主渲染成功。
