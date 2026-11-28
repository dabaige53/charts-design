# 本地 MCP 安装与更新

`charts-design-runtime` 和直接二进制 `charts-design-core` 使用同一套命令。安装包提供两个 Skill 与共享 UI，原生程序按操作系统和架构选择；无需 Python 环境。

## 安装

通过 npm 包启动；安装阶段下载与软件包版本一致的平台程序并验证 SHA-256 和实际版本，已安装的同版本程序不重复下载：

```sh
npx --package charts-design charts-design-runtime mcp --runtime-root /absolute/path/runtime-cache
```

稳定安装可用 `npm install -g charts-design`，再运行同一 `charts-design-runtime` 命令。`charts-design` 是统一命令的简写。npm 启动器使用 Node.js；Bun 只用于源码依赖、前端构建和开发脚本。

如果安装时显式禁用了生命周期脚本，先执行一次 `charts-design-runtime install-native`。受控离线环境可以设置 `CHARTS_CORE_BIN` 指向已有程序；安装阶段会验证它与包版本一致。`CHARTS_SKIP_NATIVE_INSTALL=1` 显式跳过原生下载，适用于随后自行构建的源码环境。

源码开发先执行 `bun run setup`，用 `bun run native:install` 安装与包版本匹配的程序，或用 `bun run native:build` 从锁定 Cargo 依赖构建。需要预览时执行 `bun run ui:prepare`；产物相符时直接复用。

原生程序安装到 `runtime-core/native/<平台>-<架构>/`。下载必须验证 SHA-256 并通过实际版本检查，成功后原子替换；失败保留现有安装。可用 `CHARTS_CORE_BIN` 指定已有程序的绝对路径。运行时不临时下载依赖。

MCP 客户端只配置一个入口，每个项目请求显式携带 `projectRoot`。业务资产与安装目录分开，更新程序不搬移项目，也不为每个业务项目复制一个 MCP 服务。

## 更新

更新到明确的软件包版本，保留项目目录、运行缓存目录、来源别名与现有访问配置。源码安装同步更新原生程序和 `runtime-ui/dist/`；只复制界面不会更新后端。

重新连接 MCP 后重新读取工具列表，并打开新预览。协议工具与界面资源的构建标识用于确认连接版本；已经打开的页面不会因为磁盘文件更新而自动替换。

## 确认生效

1. 对目标项目调用 `runtime_info`，核对 `moduleRoot`、`backendBuildId`、`uiBuildId`、进程编号和资产路径。
2. 从该连接调用 `dashboard_preview` 并打开当前 UI 资源；过期 URI 会返回 `UI_BUILD_EXPIRED`。
3. 核对草稿与已保存版本、筛选、导出和所需宿主能力。刷新报表只刷新数据。

自动检查、已连接进程、真实宿主显示和线上部署分别确认。构建与本地检查范围见[开发检查](testing.md)。
