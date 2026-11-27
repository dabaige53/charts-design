# Magpie 双后端 MCP 交接

## 接手目标

在目标服务器上，让 Codex 通过 Magpie 的一个 `charts-design` 条目访问自托管和 CloudBase 两个后端。所有项目继承 Codex 全局的 Magpie 接入。只在 Magpie 管理 Charts Design 的客户端注册。

自托管后端的 `/unified/mcp` 按 `projectRoot` 路由。现有项目只在一边时自动选定后端。同名或新建项目时显式传 `backend: "server"` 或 `"cloudbase"`。已有归属保存在网关的 `backend-routes.sqlite3`。两端原有 MCP 服务仍供网关及运维使用。这是当时的路由规则。当前部署入口见[自有服务器与 Neon](../operations/self-hosted-server.md#自有服务器与-neon)。

## 已完成

2026-11-24，源机器上的 Magpie 原先将 `charts-design` 指向 CloudBase。已替换为仅限本机、分发给 Codex 的同名条目。它以 stdio 启动固定版本 `mcp-proxy`，转接到自托管后端的 `/unified/mcp`。统一令牌通过进程环境注入。源机器的 Codex 项目级 CloudBase 直连已移除。

通过 Codex 全局配置中的 Magpie HTTP 入口实测列出 62 个工具，`dashboard_create` 的 `backend` 参数包含两种后端。以不存在的随机项目调用 `runtime_info`，返回 `PROJECT_NOT_FOUND`。该结果表明网关查完两边的项目目录。转接器的工具列表保留了 `dashboard_preview` 的应用元数据。此次未操作真实看板、检查宿主内预览、生成编辑链接或修改后端部署。

这个 PR 交付交接说明。Magpie 条目、Codex 本机配置和凭据映射需要在目标服务器上单独配置。仓库的 `mcp.json` 是本地开发及协议检查入口。

## 在目标服务器接入

1. 核对目标服务器的 Codex 全局配置已由 Magpie 分发。检查 Magpie 资源库和 Codex 用户级、项目级配置。记录已有 `charts-design` 条目的分发范围，确认只替换 Charts Design 的旧条目。
2. 取用[当时的统一 MCP 配置示例](https://github.com/dabaige53/charts-design/blob/486bd637f59b824a30f9e990cfa0ed8f8d9d3906/deploy/neon/unified-mcp.example.json)中的地址。让目标服务器的私有运行入口向子进程注入 `CHARTS_UNIFIED_TOKEN`。使用目标机器已授权的凭据映射，确认 Magpie 的运行账号可读。
3. 使用目标服务器上的 `uvx` 准备 `mcp-proxy==0.15.0`。启动命令使用目标机实际路径，并在同一个进程内将 `CHARTS_UNIFIED_TOKEN` 映射到 `API_ACCESS_TOKEN`。以下命令应由私有凭据入口启动。先确认转接器能完成 MCP 初始化和 `tools/list`。

   ```sh
   export API_ACCESS_TOKEN="$CHARTS_UNIFIED_TOKEN"
   unset CHARTS_UNIFIED_TOKEN
   exec uvx --offline --from mcp-proxy==0.15.0 mcp-proxy \
     --transport streamablehttp "$CHARTS_MCP_URL"
   ```

   `CHARTS_MCP_URL` 使用示例中的完整 `/unified/mcp` 地址。先执行 `uvx --from mcp-proxy==0.15.0 mcp-proxy --version` 准备离线启动所需的缓存。凭据入口、`uvx` 和 CLI 调用应以 Magpie 实际运行账号验证。
4. 在 Magpie 中用该命令注册仅限目标机的 `charts-design`，并分发给 Codex。源机器的 Magpie 无法用 `library mcp here` 给 URL 条目覆盖命令，`library mcp add` 也拒绝同名覆盖。先验证新命令并保有可恢复的旧配置，再通过 Magpie 替换原条目。移除目标 Codex 的 Charts Design 直连注册。重新打开 Codex 会话加载配置。

## 接手验收

- 在一个非 Charts Design 的 Codex 项目中检查，只由 Magpie 提供 `charts-design` 工具。确认 `dashboard_create` 暴露两个 `backend` 值。
- 通过 Magpie 对一个已知自托管项目和一个已知 CloudBase 项目分别调用 `runtime_info` 或 `dashboard_list`，传入各自的 `projectRoot`。核对结果来自预期后端。测试同名项目时，先确认网关现有归属，再决定是否传 `backend`。
- 如果后续任务需要预览，在选定项目上打开一次已保存的 `dashboard_preview`，检查实际宿主能渲染。需要继续签发编辑链接时，先核对自托管项目和看板 ID，再按[自托管服务器的鉴权与访问说明](../operations/self-hosted-server.md)处理。

## 失败时检查

- `401` 时检查是否使用统一入口专用的 Bearer 令牌。`/health` 可用只证明后端在线。
- `CATALOG_UNAVAILABLE` 时检查网关到 CloudBase 项目目录的连通性及网关的 CloudBase 凭据。`BACKEND_REQUIRED` 时检查是否存在同名项目。`BACKEND_CONFLICT` 时以网关记录的归属为准。
- 如果直接 MCP 探测通过、Magpie 中找不到工具，在 Magpie 的运行账号下检查可执行文件、离线缓存和凭据读取，再检查条目的 Codex 分发状态。需要恢复接入时，先在 Magpie 内恢复该条目先前的配置。恢复到 CloudBase 地址时只能访问 CloudBase。
