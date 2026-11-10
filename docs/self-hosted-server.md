# 自托管服务器：远程 MCP 与网页预览

`python3 -m dashboard_runtime server` 在一台服务器上同时提供远程 MCP（Streamable HTTP）和看板、分析报告的网页预览。它复用本地 Runtime 的同一套 `Service`、项目存储、Doctor 与前端构建；区别在于长期运行、按项目名隔离存储、用令牌和签名链接控制访问。本地 stdio MCP（`mcp` 命令）和本机编辑器（`serve` 命令）保持不变。

> **当前状态（2026-11-10）**
> 新 React 组件和 MCP 应用通过独立构建、资源打包接入。支持 JSON、CSV、HTML 快照与静态网页导出；未构建应用资源时返回 `UI_UNAVAILABLE`。实施记录与宿主确认边界见项目 `docs/ui-refactor-plan.md`。

## 提供的入口

| 路径 | 用途 | 鉴权 |
| --- | --- | --- |
| `/mcp` | Streamable HTTP MCP 端点，供 Claude Code、Claude Desktop、IDE 等客户端连接 | `Authorization: Bearer <服务器令牌>` |
| `/mcp/<令牌>` | 同上，供无法设置请求头的客户端使用 | 路径中的服务器令牌 |
| `/view/<项目>/<看板>` | 只读预览：看板网格或学术单栏报告 | URL 片段 `#token=` 中的签名分享令牌 |
| `/edit/<项目>/<看板>` | 浏览器编辑：拖动与缩放布局、修改标题、版本历史 | 编辑权限的签名分享令牌 |
| `/` | 默认项目预览入口；跨项目管理通过 API／CLI | 服务器令牌（只保存在当前标签页） |
| `/files/<令牌>` | 导出文件下载（JSON、CSV、HTML、静态 ZIP） | 24 小时有效的签名链接 |
| `/health` | 存活检查，返回版本 | 无 |

页面外壳不含业务数据；数据只经由带令牌的接口读取。分享令牌放在 URL 片段中，浏览器不会把片段发送给服务器、代理或 Referer；页面加载后从地址栏移除，只保留在当前标签页的 sessionStorage。

## 快速开始

服务器依赖只有 `mcp>=1.28,<2`（随附 Starlette 与 uvicorn）；Seaborn 统计图独立于旧 UI，需要另装 `.[statistics]`。

本机试用：

```sh
python3 -m pip install 'mcp>=1.28,<2'
TOKEN=$(python3 -c "import secrets;print(secrets.token_urlsafe(32))")
python3 -m dashboard_runtime server --workspace ./charts-workspace --port 8000 --token "$TOKEN"
```

启动后打印 MCP 地址与管理入口。生产部署放在 HTTPS 反向代理之后，并设置对外地址：

```sh
python3 -m dashboard_runtime server --workspace /data/projects --host 127.0.0.1 --port 8000 \
  --public-url https://charts.example.com --token-file /etc/charts-design/tokens
```

`deploy/` 提供可直接改用的文件：

- `deploy/Dockerfile`、`deploy/docker-compose.yml`：纯 Python 后端镜像，以非 root 用户运行，数据卷挂载 `/data`。在仓库根目录执行 `docker compose -f deploy/docker-compose.yml up -d --build`，配置写入 `deploy/charts.env`（从 `deploy/environment.example` 复制，不提交 Git）。
- `deploy/charts-design.service`：systemd 单元，假设代码位于 `/opt/charts-design` 并使用其中的虚拟环境。
- `deploy/nginx.conf`：TLS 反向代理示例；`/mcp` 关闭缓冲以支持 SSE，`/mcp` 与 `/files/` 关闭访问日志，避免令牌进入日志。

`charts.env` 只用于容器启动时注入配置。Docker 构建采用源码白名单，并排除各层目录中的 `.env`、`*.env`、私钥及 `server-secret`；运行配置、本机工作区和业务数据不进入构建镜像。CI 放入不含真实凭据的环境文件，再检查实际运行镜像未包含这些文件，同时检查网页部署包仍可完整导出。

## 配置

命令行参数优先，其次是环境变量。

| 参数 | 环境变量 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--workspace` | `CHARTS_WORKSPACE` | 必填 | 项目根目录；每个项目一个子目录 |
| `--runtime-root` | `CHARTS_RUNTIME_ROOT` | `<workspace>/.runtime` | 缓存、诊断、签名密钥与链接状态 |
| `--host` / `--port` | `CHARTS_HOST` / `CHARTS_PORT` | `127.0.0.1` / `8000` | 容器内使用 `0.0.0.0` |
| `--public-url` | `CHARTS_PUBLIC_URL` | `http://<host>:<port>` | 链接中的对外地址；可含路径前缀，代理须去掉前缀再转发 |
| `--token`（可重复）/ `--token-file` | `CHARTS_SERVER_TOKENS`（逗号分隔）/ `CHARTS_SERVER_TOKEN_FILE` | 至少一个 | MCP 与管理入口令牌，至少 16 个字符；同时列出新旧令牌即可轮换 |
| — | `CHARTS_SERVER_SECRET` | 自动生成 | 链接签名密钥（≥32 字节）；未设置时在运行目录生成 `server-secret`（权限 600）并跨重启保留 |
| `--share-ttl-hours` | `CHARTS_SHARE_TTL_HOURS` | 168 | 分享链接默认有效期 |
| `--default-project` | `CHARTS_DEFAULT_PROJECT` | `default` | 调用省略 `projectRoot` 时使用的项目 |
| `--sources` | `CHARTS_SOURCES` | 无 | 运维方配置的只读 SQLite 来源别名 |
| `--allowed-host` | `CHARTS_ALLOWED_HOSTS` | 无 | `/mcp` 额外接受的 Host |
| `--forwarded-allow-ips` | `CHARTS_FORWARDED_ALLOW_IPS` | `127.0.0.1` | 受信任的反向代理地址 |
| `--stateless` | `CHARTS_STATELESS` | 否 | 无状态 MCP 会话，用于多副本负载均衡 |
| `--insecure-no-auth` | — | 否 | 仅限回环地址的免令牌试用 |

设置 `--public-url` 或 `--allowed-host` 后，`/mcp` 按这些地址检查 Host 与 Origin（防 DNS 重绑定）；未设置时依靠令牌鉴权，并接受任意 Host，便于局域网试用。

## 连接 MCP 客户端

Claude Code：

```sh
claude mcp add --transport http charts-design https://charts.example.com/mcp \
  --header "Authorization: Bearer <服务器令牌>"
```

支持 JSON 配置的客户端：

```json
{"mcpServers": {"charts-design": {"type": "http", "url": "https://charts.example.com/mcp",
  "headers": {"Authorization": "Bearer ${CHARTS_TOKEN}"}}}}
```

只能填写 URL 的客户端使用 `https://charts.example.com/mcp/<服务器令牌>`。该 URL 本身就是凭据，只在 HTTPS 下使用，并确认代理不记录路径。服务器不提供 OAuth 授权流程。

## 项目与存储

远程调用中的 `projectRoot` 是项目名（字母、数字、`-`、`_`，最多 64 个字符），新名字在首次使用时创建。为兼容本地 Skill，也接受工作区直接子目录的绝对路径；其他路径一律以 `PROJECT_OUTSIDE_WORKSPACE` 拒绝。每个项目的目录结构与本地项目相同（`charts-project.json`、`dashboards/`、`data/`），可整体备份或用 `migrate-project` 迁入迁出。结果中的 `projectRoot` 返回项目名，不暴露服务器路径。

远程模式隐藏 `dashboard_export_open`（它会在服务器桌面上打开文件）；导出结果改为附带 `downloadUrl`，网页部署包另带 `siteDownloadUrl`。其余工具、操作合同、编辑批次与 Doctor 规则与本地相同，见 [Runtime 说明](dashboard-runtime.md) 与 [项目资产与加载](project-runtime.md)。


## 网页预览与分享

- `dashboard_preview`：除 MCP App 所需文档外，结果附带 `previewUrl` 与 `previewExpiresAt`。不能显示 MCP Apps 的宿主（例如终端中的 Claude Code）把链接交给用户即可。仍按“批次完成后预览一次”的流程调用。
- `dashboard_share`：`access` 为 `view`（只读）或 `edit`，`expiresInHours` 为 1–8784 小时。
- `dashboard_share_revoke`：使该看板此前签发的全部链接立即失效。
- 命令行：`python3 -m dashboard_runtime share <项目> <看板> --workspace ... --public-url ... [--access edit] [--hours 24]`，只需能读取签名密钥。
- 管理入口 `/`：输入服务器令牌后列出项目与看板，点击生成 12 小时有效的预览或编辑链接。

| 权限 | 可用操作 |
| --- | --- |
| 只读链接 | 阅读看板或报告、筛选、表格分页与搜索、图表切换为表、查看指标定义与来源、导出文件、查看已有批注 |
| 编辑链接 | 另可拖动布局、修改标题与说明、编辑报告 Markdown、版本历史与恢复、运行诊断、生成网页部署包 |

链接只对签发时的项目与看板有效，访问其他看板返回 403，页面切换只列出该看板。导入数据、执行查询、新建看板等操作只通过 MCP 完成。报告在浏览器中按学术单栏排版，图表滚动到可见区域时加载。

页面以内容哈希引用 `app.<构建号>.js/css`，设置长期不可变缓存并以 gzip 压缩。响应头包含 CSP（仅允许本站脚本与经哈希固定的启动脚本）、`Referrer-Policy: no-referrer`、`X-Frame-Options: DENY`。

## 边界

- 访问控制只有服务器令牌与签名链接两层；没有用户账号、角色权限、行级权限或 OAuth。持有服务器令牌即可读写全部项目。
- 分享链接是持有即可用的凭据：转发链接等于转发权限。需要撤销时使用 `dashboard_share_revoke`，或更换签名密钥使全部链接失效。
- 查询能力仍只限运维方配置的只读 SQLite 别名；本地查询限制不是加固的多租户沙箱。
- 单进程 SQLite 存储适合团队内部规模；多副本部署需要共享同一工作区存储并使用 `--stateless`，未做并发压测。
- 网页部署包（`dashboard_export_site`）仍是独立的只读静态站点，与本服务器互不依赖，见 [静态部署包](static-deployment.md)。

## 本次验收

2026-11-07 在 Linux 容器中验证：官方 MCP Python 客户端经 Streamable HTTP 完成工具列表、创建、越界路径拒绝、预览链接、导出下载与令牌鉴权；Chromium 打开只读与编辑链接，看板与报告图表正常渲染、无脚本或 CSP 错误，伪造令牌显示失效提示，手机宽度无横向溢出。自动测试见 `tests/runtime/test_server.py`。

2026-11-08，`main` 提交 `ae77261` 的 GitHub Actions 运行 40 六个作业全部通过，包含完整 Docker 多阶段构建、以非 root 用户运行镜像、远程 MCP、预览与下载冒烟检查。详细历史见[验收记录](records/2026-11-07-server-layout-kpi.md)。

## 实际部署与客户端验收待办


真实客户端需提供可访问上述 HTTPS 地址的目标环境，以及对应客户端的远程 MCP 配置入口。按每个目标客户端实际支持的请求头令牌或 URL 令牌方式连接，完成初始化、工具发现、在隔离项目中创建和修改合成看板、打开预览、下载导出、撤销链接与重新连接。Codex、Claude Desktop、Claude Code、claude.ai 的兼容性分别记录，不用官方 Python SDK 的通过结果代替。未实现 OAuth，必须先确认目标客户端支持当前令牌接入方式；只支持 OAuth 的入口不在现有能力内。
