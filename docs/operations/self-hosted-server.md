# 自有服务器与独立分享服务

作者在本机或自有服务器制作看板和分析报告。自有服务器以 `workspace` 角色运行，提供唯一的远程 MCP 地址和同域编辑、预览。CloudBase 或 Cloudflare 以 `sharing` 角色运行，接收选定版本的发布包，提供读者页面和批注接口。本地 stdio MCP 与本机编辑器直接使用本机项目。

| 角色 | 公开地址 | 保存内容 |
| --- | --- | --- |
| 自有服务器 `workspace` | `https://<作者域名>/mcp`、`/edit/…`、`/view/…` | 项目数据、草稿、版本、项目批注和分享引用 |
| CloudBase 或 Cloudflare `sharing` | `https://<分享域名>/s/<shareId>/`、发布管理接口 | 固定版本页面、Parquet 数据、访问状态和读者批注 |
| 本机 | stdio MCP、`serve` 返回的 loopback 链接 | 本机项目与分享引用 |

作者操作、开发预览和编辑调用工作区。只有显式创建独立分享时，工作区才向分享服务提交所选已保存版本的副本。读者打开页面、筛选、翻页和提交批注均由浏览器和分享服务完成。作者按需通过工作区读取原版反馈。

## 提供的入口

| 路径 | 用途 | 鉴权 |
| --- | --- | --- |
| `/mcp` | Streamable HTTP MCP 端点，供 Claude Code、Claude Desktop、IDE 等客户端连接 | `Authorization: Bearer <服务器令牌>` |
| `/view/<项目>/<看板>` | 内容只读预览；能否新增批注由独立权限决定 | URL 片段 `#token=` 中的签名分享令牌 |
| `/edit/<项目>/<看板>` | 浏览器编辑：拖动与缩放布局、修改标题、版本历史 | 编辑权限的签名分享令牌 |
| `/` | 默认项目预览入口；跨项目管理通过 API／CLI | 服务器令牌（只保存在当前标签页） |
| `/files/<令牌>` | 导出文件下载（JSON、CSV、HTML、静态 ZIP） | 24 小时有效的签名链接 |
| `/health` | 两种角色的存活检查，返回角色、版本和发布信息 | 无 |
| `/s/<shareId>/` 及其资源 | 所选平台上的独立只读副本 | 8 位数字密钥与受限会话 |
| `/api/v1/p/<项目>/annotations/<看板>` | 工作区批注读取、追加；管理操作仅限作者 | 同一工作区签名令牌，独立校验批注能力 |
| `/s/<shareId>/api/annotations` | 对应固定分享版本的位置批注 | 该分享的有效会话及批注权限 |

页面外壳不含业务数据；数据只经由带令牌的接口读取。分享令牌放在 URL 片段中，浏览器不会把片段发送给服务器、代理或 Referer；页面加载后从地址栏移除，只保留在当前标签页的 sessionStorage。

如果访问域名的提示页在跳转时丢失了 URL 片段，或链接令牌已失效，页面会提示粘贴收到的完整在线访问链接。输入内容只在当前页面读取；恢复时仅接受当前域名和路径对应的链接，并将其中的令牌保存在当前标签页。过期或已撤销的链接须重新签发。生产使用应配置稳定的正式域名，避免依赖测试域名提示页。

## 快速开始

服务器由统一 Rust 原生程序运行，MCP、HTTP、数据、统计图与对象存储均在同一运行时实现。安装共享 UI 后即可提供页面。

本机试用：

```sh
charts-design-runtime server --workspace ./charts-workspace --port 8000 --token-file /absolute/path/tokens
```

启动后打印 MCP 地址与管理入口。生产部署放在 HTTPS 反向代理之后，并设置对外地址：

```sh
charts-design-runtime server --workspace /data/projects --host 127.0.0.1 --port 8000 \
  --public-url https://charts.example.com --token-file /etc/charts-design/tokens
```

`deploy/` 提供可直接改用的文件：

- `deploy/Dockerfile`、`deploy/docker-compose.yml`：包含 Rust 运行时与共享 UI 的镜像，以非 root 用户运行，数据卷挂载 `/data`。在仓库根目录执行 `docker compose -f deploy/docker-compose.yml up -d --build`，配置写入 `deploy/charts.env`（从 `deploy/environment.example` 复制，不提交 Git）。
- `deploy/charts-design.service`：systemd 单元，假设程序安装于 `/opt/charts-design`。
- `deploy/nginx.conf`：TLS 反向代理示例；`/mcp` 关闭缓冲以支持 SSE，`/mcp` 与 `/files/` 关闭访问日志，避免令牌进入日志。

`charts.env` 只用于容器启动时注入配置。Docker 构建采用源码白名单，并排除各层目录中的 `.env`、`*.env`、私钥及 `server-secret`；运行配置、本机工作区和业务数据不进入构建镜像。CI 放入不含真实凭据的环境文件，再检查实际运行镜像未包含这些文件，同时检查网页部署包仍可完整导出。

## 配置

命令行参数优先，其次是环境变量。

| 参数 | 环境变量 | 默认 | 说明 |
| --- | --- | --- | --- |
| — | `CHARTS_SERVER_ROLE` | 本机存储与 Neon 为 `workspace`，CloudBase 与 Cloudflare 为 `sharing` | 运行角色 |
| `--workspace` | `CHARTS_WORKSPACE` | 必填 | 项目根目录；每个项目一个子目录 |
| `--runtime-root` | `CHARTS_RUNTIME_ROOT` | `<workspace>/.runtime` | 缓存、诊断、签名密钥与链接状态 |
| `--host` / `--port` | `CHARTS_HOST` / `CHARTS_PORT` | `127.0.0.1` / `8000` | 容器内使用 `0.0.0.0` |
| `--public-url` | `CHARTS_PUBLIC_URL` | `http://<host>:<port>` | 链接中的对外地址；可含路径前缀，代理须去掉前缀再转发 |
| `--token`（可重复）/ `--token-file` | `CHARTS_SERVER_TOKENS`（逗号分隔）/ `CHARTS_SERVER_TOKEN_FILE` | 至少一个 | MCP 与管理入口令牌，至少 16 个字符；同时列出新旧令牌即可轮换 |
| — | `CHARTS_SERVER_SECRET` | 自动生成 | 链接签名密钥（≥32 字节）；未设置时在运行目录生成 `server-secret`（权限 600）并跨重启保留 |
| `--share-ttl-hours` | `CHARTS_SHARE_TTL_HOURS` | 168 | 分享链接默认有效期 |
| `--default-project` | `CHARTS_DEFAULT_PROJECT` | `default` | 调用省略 `projectRoot` 时使用的项目 |
| `--sources` | `CHARTS_SOURCES` | 无 | 运维方配置的只读 SQLite、PostgreSQL、DuckDB 来源别名 |
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

远程客户端需要能设置 `Authorization` 请求头，使用 HTTPS 传送 Bearer 令牌。

## 项目与存储

远程调用中的 `projectRoot` 是项目名（字母、数字、`-`、`_`，最多 64 个字符），新名字在首次使用时创建。为兼容本地 Skill，也接受工作区直接子目录的绝对路径；其他路径一律以 `PROJECT_OUTSIDE_WORKSPACE` 拒绝。每个项目的目录结构与本地项目相同（`charts-project.json`、`dashboards/`、`data/`），可整体备份或用 `migrate-project` 迁入迁出。结果中的 `projectRoot` 返回项目名，不暴露服务器路径。

远程模式隐藏 `dashboard_export_open`（它会在服务器桌面上打开文件）；导出结果改为附带 `downloadUrl`，网页部署包另带 `siteDownloadUrl`。其余工具、操作合同、编辑批次与 Doctor 规则与本地相同，见 [Runtime 说明](../implementation/dashboard-runtime.md) 与 [项目资产与加载](../implementation/project-runtime.md)。

## 网页预览与分享

访问方式的名称见[看板交付术语](../agent/GLOSSARY.md)。在线链接连接自有服务器项目；独立分享链接访问分享服务保存的发布副本。

| 访问方式 | 创建方式 | 数据来源及更新 | 凭据与有效期 |
| --- | --- | --- | --- |
| 在线只读链接 | `dashboard_share`，`access=view` | 自有服务器项目的已保存检查点及其数据 | 链接包含访问令牌；按 `expiresInHours` 或服务器默认值过期，可撤销 |
| 在线编辑链接 | `dashboard_share`，`access=edit` | 同一服务端项目；支持网页提供的编辑、版本管理和恢复 | 同在线只读链接，权限包含网页支持的编辑操作 |
| 独立分享链接 | 对指定保存版调用 `dashboard_share_publish` | 副本保留发布时的网页和数据；保存在腾讯云私有 COS 或 Cloudflare 私有工作区，不跟随原项目更新 | 8 位数字密钥；可选 7 天、30 天或不过期，可单独撤销 |

`dashboard_preview` 在支持 MCP Apps 的宿主中打开已保存检查点。远程工作区需要浏览器链接时使用 `dashboard_share`；本机 stdio 的预览回执另提供 `browserLinks`，可直接进入同进程提供的普通浏览器编辑和预览页。

- `dashboard_share`：`access` 为 `view`（内容只读）或 `edit`，`expiresInHours` 为 1–8784 小时。`view` 可显式设置 `annotationMode: "annotate"` 允许新增批注；默认 `view`，包括省略此字段的签名令牌，授予查看权限。
- `dashboard_share_revoke`：使该看板此前签发的全部链接立即失效。
- 命令行：`charts-design-runtime share <项目> <看板> --workspace ... --public-url ... [--access edit] [--hours 24]`，只需能读取签名密钥。
- 管理入口 `/`：输入服务器令牌后列出项目与看板，点击生成 12 小时有效的预览或编辑链接。

| 权限 | 可用操作 |
| --- | --- |
| 只读链接 | 阅读看板或报告、筛选、表格分页与搜索、图表切换为表、查看指标定义与来源、导出文件、查看已有批注 |
| 编辑链接 | 另可拖动布局、修改标题与说明、编辑报告 Markdown、版本历史与恢复、运行诊断、生成网页部署包 |
| 明确授予批注权限的只读链接 | 查看内容和新增位置批注 |

浏览器的批注读写直接走 HTTP，不通过 MCP 工具调用。工作区批注写入原项目的独立批注状态，不生成内容版本；批注上下文依据当时实际展示的检查点，不能误用最新草稿的组件与版本。

签名链接默认只包含签发时的看板；调用 `dashboard_share` 时可通过 `dashboardIds` 指定同一项目的其他页面。页面切换只列出获准页面，访问其他页面返回 403。撤销其中任一页面的签名分享会使包含它的链接失效。导入数据、执行查询、新建看板等操作只通过 MCP 完成。报告在浏览器中按学术单栏排版，图表滚动到可见区域时加载。

页面以内容哈希引用 `app.<构建号>.js/css`，设置长期不可变缓存并以 gzip 压缩。响应头包含 CSP（仅允许本站脚本与经哈希固定的启动脚本）、`Referrer-Policy: no-referrer`、`X-Frame-Options: DENY`。

## 签名预览服务的边界

- 签名预览使用服务器令牌与签名链接；云端独立副本另用下节的数字密钥。没有用户账号、角色权限、行级权限或 OAuth。持有服务器令牌即可读写全部项目。
- 分享链接是持有即可用的凭据：转发链接等于转发权限。需要撤销时使用 `dashboard_share_revoke`，或更换签名密钥使全部链接失效。
- 查询能力只限运维方配置的只读来源别名；本地查询限制不是加固的多租户沙箱。
- 作者工作区使用主机持久磁盘上的 SQLite，或 Neon PostgreSQL 与自有服务器的持久卷。配置与查询边界见[项目存储](../implementation/project-runtime.md#存储)。
- 网页部署包（`dashboard_export_site`）仍是独立的只读静态站点，与本服务器互不依赖，见 [静态部署包](static-deployment.md)。

## 本机通过分享服务发布

本机和自有服务器都使用同一个分享协议。工作区保存项目数据、编辑历史与私人批注，发布时只向已部署的分享服务发送选定版本的副本。每次发布复用服务和分享域名。

在作者进程的环境中配置以下变量，适用于本机 `serve`、本机 stdio MCP 和自有服务器：

| 环境变量 | 内容 |
| --- | --- |
| `CHARTS_SHARE_SERVICE_URL` | 既有分享服务的 HTTPS 根地址，可含原有路径前缀；仅本机验证允许 loopback HTTP |
| `CHARTS_SHARE_SERVICE_TOKEN` | 分享服务自己的 Bearer 令牌，仅保存在作者进程。与作者工作区 MCP 令牌分别配置 |
| `CHARTS_SHARE_SERVICE_PROJECT` | 分享服务侧的发布命名空间，默认 `default`。发布归属还包含每个作者项目的独立来源标识 |
| `CHARTS_SHARE_PARQUET_LAYOUT` | 目标是 Cloudflare Pages 快照时设为 `single`，每个数据集导出一个 Parquet。默认 `sharded` 适用于其他分享服务 |

使用本机入口打开项目，例如：

```sh
charts-design-runtime --project-root /absolute/path/project \
  --runtime-root /absolute/path/runtime-cache serve --dashboard overview
```

1. 使用启动回执的 `editUrl` 编辑、保存；`viewUrl` 查看最新已保存版本并批注。本地和远程 MCP 的 `dashboard_preview` 都返回 `browserLinks.editUrl` 和 `browserLinks.viewUrl`。远程链接使用作者服务器的公开地址。
2. 在编辑页选择已保存版本和「仅查看」或「可批注」，点击「分享此版本」。服务检查并打包该版本，成功后返回独立 `accessUrl`。要更新正式发布版，另行点击「设为正式发布版」。
3. 读者在分享链接查看、筛选、分页，并按授权新增批注。作者电脑可以关机；页面、数据和批注均由分享服务提供。
4. 作者回到该项目的「版本与分享 → 分享」，在对应记录点击「查看读者批注」。每次打开或重新读取才向服务请求；反馈在原分享版本打开并定位，不合并到当前草稿。即使当前草稿移除组件，原分享中的锚点仍可读取。

作者工作区在 `dashboards/share-references.sqlite3` 保存来源标识、请求状态与分享引用，需随项目备份。没有双向同步、常驻同步进程或自动合并。前端对不确定的发布回执保留请求 ID；本机重试同一请求时复用已生成的 ZIP 与校验值。未完成请求所需的导出文件丢失时明确报错，不静默创建第二份分享。

作者进程通过管理接口 `POST /api/v1/publications` 上传固定版本 ZIP；服务校验文件路径、版本与资源，使用服务器自己的 UI，仅发布包中使用的数据。`GET/DELETE /api/v1/publications/<shareId>` 校验服务令牌和来源归属，分别读取反馈、撤销分享。本机浏览器只访问本机代理 `/api/publications/<shareId>/feedback`；远程作者页面使用 `/api/v1/p/<项目>/publications/<shareId>/feedback`。浏览器不会得到服务 Bearer 或云管理令牌。

反馈页采用 15 分钟的签名反馈链接，并再次检查分享有效性；只允许读取该分享的批注。已有访客会话打开反馈链接会切换为只读反馈会话，再打开原密钥链接会恢复该分享授予的权限。不是用户账户认证：读者显示为访客或未经验证的自填署名。

### 各部署路径的持久化职责

| 路径 | 固定版本、页面与查询数据 | 分享批注的写入与持久化 |
| --- | --- | --- |
| CloudBase + 私有 COS | 既有 HTTPS 网关鉴权；COS 保存独立副本及 Parquet 数据 | Runtime HTTP 接口调用 PostgreSQL `charts_share_annotations` RPC；按分享 ID、页面和发布版本独立保存 |
| Cloudflare Worker + Container | Container 提供页面与数据；既有 Durable Object SQLite 工作区 checkpoint 跨冷启动恢复 | 每个分享独立 SQLite；每次成功批注在返回前只保存该 SQLite 的增量 checkpoint，不重新归档网页或 Parquet |
| Cloudflare Pages + D1 | Pages 保存固定页面定义与 Parquet，每个数据集一个文件 | Pages Functions 检查访问密钥和批注权限，D1 保存分享对应关系、期限和批注 |
| Cloudflare Pages 分享代理（可选） | Pages 转发分享资源，由分享源站提供副本 | 分享源站持久化批注 |
| 纯静态 ZIP | 包内页面与使用中的完整数据 | 无后端，不提供可提交状态 |

CloudBase 启用可批注分享或本机发布桥前，需要由部署人员应用 `cloudbase/migrations/20261127010000_share_annotations.sql`，并更新网关；该迁移只新增分享批注存储与服务端 RPC，不迁移现有业务数据。缺少持久化能力会拒绝新请求。旧仅查看分享保持原行为，不会自动获得写权限。Cloudflare 需要同步更新 Worker 与 Container；Pages 路径需要更新代理和后端，不能只上传静态文件。

本机和自有服务器的发布入口均接受单个已保存看板或报告，使用分享服务生成的访问密钥。所有路径都沿用到期、撤销和清理机制。分享过期或撤销后，页面和批注的新读写均被拒绝；清理同时删除该分享的批注。

清理后只保留不含作者、密钥、页面、数据或批注的退役分享 ID，用来拒绝重放旧发布请求，防止原链接复活。发布的暂存占位与激活相互校验，未激活的中断请求可由既有清理任务回收；成功回执只能在固定副本和批注作用域均就绪后返回。

## 自有服务器存储

自有服务器设置 `CHARTS_SERVER_ROLE=workspace`，`CHARTS_PUBLIC_URL` 使用作者域名。客户端配置 `https://<作者域名>/mcp` 与作者服务器的 Bearer 令牌。可以参考 [MCP 客户端配置](../../deploy/mcp.example.json)。

新部署使用 `deploy/docker-compose.yml` 和服务器磁盘上的 SQLite。作者服务的 `/health` 返回 `storage: "sqlite"`。通过服务器发布流程构建的镜像在 `release.commit` 返回构建提交号。启用前检查目标版本和存储类型。

已有 Neon 工作区继续使用当前数据库和持久卷。维护该部署时，`deploy/neon/compose.yml` 只向主机回环地址发布 `18160`，数据库、工作区卷和应用独立维护。以数据库所有者的直连 `DATABASE_URL` 和 `CHARTS_NEON_RUNTIME_ROLE` 运行 `charts-design-runtime migrate-neon`，应用容器使用权限限定的数据库账号。备份覆盖数据库与持久卷。

需要发布时，在作者服务器设置 `CHARTS_SHARE_SERVICE_URL` 和该分享服务的凭据。作者域名直接提供页面、资源、编辑和预览 API。

### 可选的 Cloudflare Pages 分享域名

如需以 Pages 域名公开读者链接，运行 `bun deploy/pages/build.mjs <输出目录>`，把生成的分享代理部署到 Pages。绑定 `ORIGIN_URL` 到运行 `sharing` 角色的 HTTPS 源站。Pages 的 `ORIGIN_TOKEN` 与源站的 `CHARTS_ORIGIN_TOKEN` 配对。源站 `CHARTS_PUBLIC_URL` 使用 Pages 公开地址，使读者链接和表单来源对应。

Pages 只转发 `/s/…`、发布管理接口和健康检查。工作区页面和 MCP 地址使用自有服务器域名。该代理独立打包，分享页资源由发布副本提供。

### Cloudflare Pages 与 D1 直接分享

在源码目录用 `bun run deploy:init -- author|pages|all` 初始化。加 `--plan` 查看目标。

```sh
bun run deploy:init -- all --plan
bun run deploy:init -- all
```

- `author` 需要 Docker Compose。复制 `deploy/environment.example` 到 `deploy/charts.env`，设置作者 HTTPS 地址和 MCP 令牌。在启用分享时配置 `CHARTS_SHARE_SERVICE_URL` 及发布令牌。可设置 `CHARTS_AUTHOR_ENV_FILE` 和 `CHARTS_AUTHOR_PORT` 指定配置文件和回环端口。由现有 HTTPS 反向代理暴露 MCP 地址。
- `pages` 从环境读取 `CLOUDFLARE_ACCOUNT_ID`、`CLOUDFLARE_API_TOKEN`、`CHARTS_PAGES_DEPLOY_TOKEN`、`CHARTS_SHARE_SERVICE_TOKEN` 和 `CHARTS_SHARE_SIGNING_SECRET`。初始化令牌需要 Pages 和 D1 写权限。快照部署令牌单独签发，只授予 Pages 写权限，由 Pages Functions 使用。脚本创建或复用 Pages 与 D1，执行 `deploy/pages/schema.sql`，绑定 `SHARE_DB`，启用 fail-closed 后发布。可设置 `CHARTS_PAGES_PROJECT`、`CHARTS_D1_DATABASE`、`CHARTS_PAGES_BRANCH` 和 `CHARTS_PAGES_URL`。
- `all` 先检查作者配置，再部署 Pages，最后启动作者容器。两个环境使用同一个发布令牌。现有 Pages 密钥在重复运行时保留。签名密钥用于保护已发链接和会话，应随环境长期保存。预览项目可使用独立的数据库和密钥。

`/health` 返回 `role: "sharing"`、`storage: "pages+d1"` 和界面构建号后，把作者环境的 `CHARTS_SHARE_SERVICE_URL` 指向 Pages 域名，设置同一发布令牌和 `CHARTS_SHARE_PARQUET_LAYOUT=single`。分享 ZIP 上限 16 MiB，快照中的 Parquet 文件合计上限 24 MiB。

每个新分享生成新的分享 ID 和一次 Pages 生产部署。新部署保留所有有效分享的页面和数据，旧链接继续使用原来的 `/s/<shareId>/` 地址。选择「不过期」的分享不受 Cloudflare 旧部署保留期影响。重复提交同一个请求 ID 会返回原分享。读取时 Pages Functions 先检查会话和分享状态，再返回部署内的静态文件。直接访问快照文件路径会被拒绝。

撤销或到期会立即阻止读取。后续部署从当前部署清单移除失效快照。作者可在分享记录里检查清理状态，确认当前部署已移除资源。历史部署仍受同一访问检查，保留期由 Cloudflare 管理。既有 D1 分享撤销时会立即删除数据分片和批注。使用 `deploy:init` 升级时会把有效快照加入新部署清单。

## Cloudflare 独立部署

Cloudflare Worker 将发布、读者访问和批注请求送入 `sharing` 角色的 Container。Durable Object SQLite 保存副本、签名状态与批注的恢复数据。作者使用自有服务器或本机工作区。

在 GitHub 仓库的 Actions 配置中选择部署平台：

| 仓库变量 `CHARTS_DEPLOY_PROVIDER` | 发布标签时执行 |
| --- | --- |
| 不设置或 `cloudbase` | CloudBase 任务 |
| `cloudflare` | 仅 Cloudflare 任务 |

Cloudflare 账号须能使用 Workers、Containers 和 SQLite Durable Objects。配置仓库变量 `CLOUDFLARE_ACCOUNT_ID`、`CHARTS_PUBLIC_URL`（此 Worker 的 HTTPS 根地址，不带路径或末尾斜杠）。设置两个独立的 Actions Secret：`CLOUDFLARE_API_TOKEN` 用于部署，`CHARTS_SERVER_TOKENS` 用于发布管理，不能复用。默认 Worker 名为 `charts-design`，可使用其 `workers.dev` 地址；自定义域名需先绑定。

按下节的版本标签流程发布，或在 **Cloudflare release** 中选择已有版本标签。工作流构建镜像，配置 Worker 与每六小时一次的 Cron，并以 `/health` 返回的 Git 提交号检查发布结果。首次成功清理前不允许创建独立分享。发布、访问密钥、有效期和撤销使用分享服务接口。

本地部署入口是 `bun run deploy:cloudflare`，需要可用的 Docker 构建器、已注入的 Cloudflare 账号和部署凭据，以及 Worker 的 `CHARTS_SERVER_TOKENS` secret。用 `--var "CHARTS_PUBLIC_URL:$CHARTS_PUBLIC_URL"` 指定已绑定的地址。不要删除或更名已投入使用的 Durable Object 命名空间或 `workspace` 实例；新实例使用独立的分享存储。

此路径使用一个分享存储实例。请求按顺序执行。创建、撤销分享和定时清理在返回前保存分享存储的完整归档。`/s/<shareId>/api/annotations` 的成功写入只保存该分享批注 SQLite 的增量归档，冷启动先恢复内容，再恢复批注增量；下一次完整 checkpoint 成功后原子清除已包含的增量。恢复或保存失败时请求失败，不以空工作区继续。归档大小会影响完整保存的耗时，暂存新归档时还需要容纳上一份归档；不提供跨实例横向写入。清理移除当前工作区中的副本，平台灾备保留期不等同于在线访问期。

## 按版本自动发布到 CloudBase

GitHub Actions 工作流 `.github/workflows/cloudbase-release.yml` 监听 `vX.Y.Z` 标签。根目录 `package.json.version` 是服务发布号，原生版本由 Cargo 声明。先提交需要上线的源码和工作流，再运行：

```sh
bun run release -- 1.2.1
```

替换为高于当前版本的新版本号。脚本要求工作区干净，更新 `package.json`，创建版本提交和附注标签，然后只推送该标签。其他改动须提前提交；脚本只推送标签，分支与原有全量测试流程保持原状。版本提交仍留在当前本地分支，后续按正常流程合并。加 `--dry-run` 只检查条件和展示步骤，不写文件或推送。

发布任务使用项目固定版本的 Bun 和固定版本的 CloudBase CLI。GitHub 运行发布脚本的局部测试，CloudBase 根据 `deploy/Dockerfile` 构建 React 与 Rust 运行镜像，并完成完整发布；不在本机重复构建。工作流中的并发组禁止打断正在执行的部署。推送标签须使用用户或发布机器的 Git 凭据，不使用另一个工作流的默认 `GITHUB_TOKEN`，以免无法触发后续工作流。

仓库 Settings → Secrets and variables → Actions 需要以下配置：

| 类型 | 名称 | 用途 |
| --- | --- | --- |
| Secret | `CLOUDBASE_API_KEY` | 当前 CloudBase 环境的服务端 API Key |
| Variable | `CLOUDBASE_ENV_ID` | 目标环境 ID |
| Variable | `CLOUDBASE_SERVICE` | 已部署的云托管服务名 |
| Variable | `CLOUDBASE_REGION` | 服务所在区域 |
| Variable | `CLOUDBASE_SERVICE_URL` | 服务的 HTTPS 根地址 |

本机复用部署入口时，使用 `bun install --frozen-lockfile` 安装项目锁定的 `@cloudbase/cli`，通过项目凭据入口注入上述通用环境变量，并检出目标标签，执行 `bun run deploy:cloudbase -- v1.2.1`。脚本用于更新已有 CloudBase 服务，不负责首次创建 PostgreSQL、COS、API Key 或清理函数。

部署前读取现有环境变量并保留，只更新 `CHARTS_RELEASE_VERSION` 和 `CHARTS_RELEASE_COMMIT`。源码包排除环境文件、密钥文件、依赖缓存、构建产物和设计归档。密钥不写入镜像、仓库、日志或工作流摘要。

若已有云端发布任务未结束，脚本停止，避免 CLI 取消其他任务。已构建完成、健康检查通过并承接 100% 流量的灰度版本会先完成发布状态，再提交新版本；部分流量灰度需要先由维护者完成或撤回。部署命令等待云端任务结束，随后检查 `/health` 的版本号与 Git 提交号，旧实例返回成功不算本次发布通过。

成功结果显示在 GitHub Actions 的 `CloudBase release` 摘要。失败或超时会使任务失败；超时后云端任务可能仍在执行，应先看云托管构建记录再重试。需要重跑已有标签时，在 Actions 中重新运行该任务；工作流合入默认分支后，也可通过 `Run workflow` 输入已有标签。数据库回滚、SQL 迁移、SCF 清理函数更新和已分享的 COS 静态快照更新须按对应章节单独处理。

## 部署确认

对每个目标客户端，用作者域名的 HTTPS MCP 地址和 Bearer 请求头完成初始化、工具发现、在隔离项目中创建和修改合成看板、打开预览、下载导出与撤销链接。客户端验收分别记录。分享服务的 `/health` 应显示 `role: sharing`，然后用一个固定版本核对读者访问、批注和作者反馈。

## 腾讯云在线分享与云端清理

腾讯云分享保存一份独立、内容只读的看板或分析报告副本。网页、运行资源、使用中的完整数据集分片和访问控制记录保存在私有 COS。访客通过 HTTPS 网关访问，输入 8 位数字访问密钥后阅读；浏览器不会获得公开 COS 地址。

清理任务由腾讯云 SCF 定时触发执行，不由本地 MCP、用户电脑或网页网关进程执行。删除范围包括该分享副本的对象历史版本、删除标记、密钥哈希与清理任务记录。本地项目原稿和其他分享副本保留。

### 从作者工作区发布

用 `dashboard_submit` 保存内容，再调用作者工作区的 `dashboard_share_publish`，传入已保存的 `revision` 和 UUID v4 `requestId`。可选 `expiration`（`7d`、`30d`、`never`）及 `annotationMode`（`view` 或 `annotate`）。Web 版本中心的「分享此版本」使用相同入口。回执不确定时，沿用原请求 ID、版本和选项重试。

结果包含 `shareId`、`url`、`accessUrl`、`accessKey`、`revision`、`annotationMode`、`expiration`、`expiresAt` 和 `cleanupExecutor`。`expiresAt` 是 UTC Unix 秒数，不过期时为 `null`。腾讯云的清理执行方为 `tencent-scf`。

`url` 不含密钥；`accessUrl` 使用 `url#key=访问密钥`，浏览器读取片段后自动填入并从地址栏移除。片段不发送给服务器；表单仍通过 HTTPS POST 校验密钥。带密钥链接只在新建或替换分享时返回；COS 控制记录和状态接口只保留不含密钥的信息。已有 `url` 可由持有者在本机追加同样的片段使用。

登录页采用居中表单，支持窄屏和键盘操作。表单响应使用 `Referrer-Policy: same-origin`，避免浏览器在 `no-referrer` 下将 POST 来源置为 `null`；服务器继续拒绝 `null` 和其他站点的 Origin。样式及自动填入脚本使用随机 CSP nonce，来源错误和密钥错误均显示在表单内。

`dashboard_share_status` 查询本项目、本看板的分享任务，可传入一个 `shareId`。它不返回访问密钥。响应不确定时先查询，再决定是否重发。

`dashboard_share_replace` 以选定的保存版创建替代分享，保留原分享的批注权限。新副本上传完成后撤销旧分享，并返回新链接和新密钥。若 `previousRevoked=false`，保留新凭据，并按 `followUp` 撤销旧分享。

`dashboard_share_delete` 撤销一个 `shareId`，立即阻止访问，并将物理删除交给 SCF。`cleanupState=pending` 表示等待清理或重试。作者工作区保留该分享的撤销引用。此操作也适用于不过期分享。

原 `dashboard_share` 和 `dashboard_share_revoke` 继续用于自托管服务的签名预览链接；它们不创建或删除 COS 分享副本。

### 云端组成

| 组成 | 职责 |
| --- | --- |
| HTTPS 网关 | 以 `sharing` 角色运行 Runtime，提供 `/s/<shareId>/` 密钥表单、会话和逐文件鉴权。每次请求都检查到期时间 |
| 私有 COS | 保存独立网页与数据；对象不公开，响应设置 `no-store` |
| PostgreSQL 分享批注 RPC | 仅服务端可调用；校验分享版本、权限、过期、撤销与重复提交，独立保存批注，不生成内容版本 |
| SCF 云函数 | 每 6 小时扫描清理任务；删除到期、撤销或中断上传的副本；删除失败保留任务并使函数调用失败，后续触发继续重试 |

密钥会话使用 `Secure`、`HttpOnly`、`SameSite=Strict` Cookie。密钥输入有按分享和访客计数的尝试限制。网页资源、Worker 和数据分片均通过网关读取，不能绕过密钥直接访问。

到期即拒绝新的云端读取。SCF 每 6 小时触发，正常情况下物理删除需等待最多一个周期，额外耗时由数据量和云端请求决定；失败后在下一个周期重试。清理覆盖当前对象、所有历史版本和删除标记；任何批次删除失败都不能将任务标记为完成。

新发布前会检查 SCF 最近 7 小时内是否完成过一次成功清理，为 6 小时触发周期保留 1 小时余量。没有有效清理状态时返回 `CLOUD_CLEANER_UNAVAILABLE`，不会上传新副本。上传开始前先保存清理任务；中断的上传一小时后进入待清理状态，等待下次 SCF 执行。发布过程使用操作系统临时目录，上传结束或失败后删除，兼容 macOS 与 Linux 容器。

### 配置

部署环境使用通用环境变量。COS 支持执行角色注入的临时凭据；设置 `CHARTS_COS_AUTH=cloudbase` 时使用服务端 CloudBase API Key 换取临时凭据，并在运行期间刷新。网页中不包含云凭据。

| 环境变量 | 分享网关 | SCF |
| --- | --- | --- |
| `CHARTS_PUBLIC_URL` | 必填，已部署网关的 HTTPS 地址，可含路径前缀 | 不需要 |
| `CHARTS_COS_REGION` | 必填，COS 地域 | 必填，同一地域 |
| `CHARTS_COS_BUCKET` | 必填，专用于分享的私有存储桶 | 必填，同一存储桶 |
| `CHARTS_COS_SHARE_PREFIX` | 默认 `charts-shares/`，非空独立前缀 | 必须与发布进程相同 |
| `TENCENTCLOUD_SECRETID`、`TENCENTCLOUD_SECRETKEY`、`TENCENTCLOUD_SESSIONTOKEN` | 执行角色方式下由环境提供；临时凭据需包含 Token | 执行角色方式下每次调用重新读取 |
| `CHARTS_COS_AUTH=cloudbase`、`CLOUDBASE_ENV_ID`、`CLOUDBASE_API_KEY` | 使用服务端环境密钥换取并刷新 COS 临时凭据 | 当前部署使用同一方式，不依赖本地进程 |

自托管镜像包含原生对象存储客户端；凭据仅由运行环境提供。

存储桶必须私有；禁止匿名访问，分享前缀禁用额外复制、备份和 CDN 缓存。发布前检查桶 ACL 和匿名访问策略。桶权限由部署人员配置；清理程序删除配置存储桶中的分享对象。

### 部署 SCF 定时任务

源码位于 `deploy/tencent-cleaner/`。使用该目录 Dockerfile 构建 Rust 清理镜像，并推送到部署账号可读取的镜像仓库：

```sh
docker buildx build --platform linux/amd64 \
  -f deploy/Dockerfile --target cleaner -t <镜像仓库>/charts-cleaner:<版本> --push .
```

将镜像部署为 [SCF 镜像事件函数](https://cloud.tencent.com/document/product/583/56051)：

- 启动原生命令 `charts-design-core cleanup-server`，监听 `0.0.0.0:9000`，在 `/event-invoke` 接收事件。
- 配置上表中的 COS 地域、桶和前缀。
- 采用已有执行角色或 `CHARTS_COS_AUTH=cloudbase` 服务端凭据方式。执行角色权限应限于分享前缀：列举当前对象和历史版本、读取清理任务、删除对象及其历史版本、写入 `cleaner-status.json`。函数不创建或扩大角色权限。
- 添加定时触发器。使用 `deploy/tencent-cleaner/timer.json`，Cron 为 `0 0 */6 * * * *`，每 6 小时一次，并启用触发器。已有部署应先发布支持 7 小时状态有效期的网关，再更新触发器。
- 开启函数失败告警。部分删除失败时函数抛错，任务继续保留，下一次定时触发重试。
- 等待首次成功调用，再发布分享。发布工具会检查云函数保存的清理状态。

SCF 按云端计划独立执行原生清理。作者电脑关闭时，SCF 继续按计划清理。操作员手动执行 `cleanup` 时须使用同一部署环境和受限凭据。

### 检查边界

后端局部检查覆盖密钥访问、每个文件的鉴权、七天/三十天到期、不过期、主动撤销、物理版本删除、清理失败重试、SCF 环境限制，以及保留原稿和其他副本。

上线时须在目标账号验证一次发布、密钥访问、到期删除和重试，并确认云端触发器在本地进程退出后仍执行。

维护时机：服务器配置、鉴权、分享、存储或云端清理方式改变时更新；历史验收结论不替代目标部署确认。

### 从本地项目迁移选定数据

此流程用于自有服务器的 Neon 作者工作区。数据迁移使用 `dataset_transfer_chunk`、`dataset_transfer_finish`、`dataset_transfer_status` 和 `dataset_transfer_cleanup`。目标支持批量上传时，客户端在发送前压缩，每个数据版本按 5,000 行分片（末片可更少），每片最多 8 MiB gzip、16 MiB 解压后 JSON。客户端直接传给 MCP，不需要另开存储或配置存储凭据。旧服务、已有的旧格式续传，以及新任务显式使用 `--legacy` 时，仍使用 250 行、2 MiB JSON 分片。

批量上传的分片、状态查询和合并请求都带 `encoding: gzip-json-v1`。相同传输 ID 和分片编号重试时，解压后的内容必须一致。分片先放到服务端已有的私有对象存储，服务端按序重算完整数据版本，持久保存后才可引用：Neon 作者工作区写入 PostgreSQL 业务分块。完成后删除该传输的暂存对象及历史版本。中断可继续；主动放弃时调用 `dataset_transfer_cleanup` 并指定传输 ID。服务重启后状态可能为 `unknown`，重新调用 `dataset_transfer_finish`；返回 `cleanup_required` 时也调用 finish 完成清理。迁移沿用服务端既有存储权限，不自动更改权限。

`charts-design-runtime transfer` 从用户审核的清单读取本地草稿与选定数据集，通过上述 MCP 工具传输。清单包含本地 `projectRoot`，每页的 `dashboardId`、`draftRevision`、`componentCount`，以及每个选定数据集的 `id`、`version`、`rowCount`、`bytes`。客户端拒绝版本变化或清单缺少组件绑定的数据，保留组件、筛选、选定数据集的全部指标与批注；其他未选数据集及其指标不进入迁移副本。相同数据版本只传输一次。它创建新页面，不覆盖不同内容的现有页面；目标页面的版本从 1 开始，本地历史不会迁入。来源执行认证状态会标为 supplied。

在私有进程环境中设置 `CHARTS_SERVER_TOKENS` 和 `CHARTS_MCP_URL=https://<作者域名>/mcp`。客户端使用令牌列表中的第一个值。状态文件保存可续传 ID。

```sh
charts-design-runtime transfer \
  --manifest /absolute/path/online-migration-manifest.json \
  --project <远程项目名> --state /private/tmp/charts-transfer-state.json
```

迁移完成后逐页运行 `dashboard_submit` 检查并保存，然后按需要分享保存版本。传输中止或清理失败时保留状态文件并使用相同参数重试；不要删除该文件后盲目重传。用户决定放弃时，从状态文件的 `uploads` 中取得对应 ID，调用 `dataset_transfer_cleanup`，并确认成功。不会自动清理无人恢复的中断传输。

合并时，`dataset_transfer_status` 的 `phase` 标明读取暂存分块、保存数据库分块或清理；`completed` 和 `total` 对应当前阶段。客户端记录已完整暂存的版本，恢复时不再发送这些数据行。只有在已确认某个版本全部分块均已暂存的情况下，才在恢复命令中加 `--resume-staged <完整数据版本号>`；缺块时合并报错，不会创建不完整的数据版本。

### 更新已有看板的数据

自有服务器的 SQLite 工作区和已有 Neon 工作区都支持用 `charts-design-runtime remote upload` 单独上传数据版本。SQLite 在项目的私有运行目录暂存分片，校验完整数据版本后写入本地数据仓库。上传完成后，客户端保存可用于 `put_dataset_ref` 的完整引用。页面的组件、指标、筛选和发布版本由后续编辑流程维护。

```sh
charts-design-runtime remote upload \
  --project <远程项目名> --root <本地项目目录> \
  --ref /private/tmp/dataset-ref.json \
  --state /private/tmp/dataset-upload-state.json \
  --output /private/tmp/verified-ref.json
```

已有本地数据版本使用 `--ref`；新数据使用 `--rows /path/rows.jsonl --fields /path/fields.json` 替换 `--ref`，按字段定义导入 `--root/data` 后上传。`--rows` 接受 JSON 数组或 `.jsonl` 文件；大型来源优先 JSONL。准备新数据时指定独立的本地工作目录，避免与业务加工进程同时写同一数据仓库。

两个上传入口均支持 `--check-only`：检查本地引用、全部分片大小、行数和目标工具能力，不上传。使用 `--rows` 时仍会准备本地数据版本。远程续传要求 `dataset_transfer_status` 支持 `parts`；缺少该能力时，在发送数据前提示升级。上传日志区分分片数、已复用分片数、实际发送的数据字段字节数和请求耗时。原生程序版本不匹配时先更新安装，运行时不临时安装依赖。

上传默认并发 4 块，`--concurrency 1` 可用于单请求排错，最大值为 4；数据集之间顺序执行。首次上传直接发送；中途恢复时按窗口查询服务端 `receivedParts`，比较暂存 JSON 的 SHA-256，仅发送缺失块。客户端即使在收到确认前退出，也能恢复。校验值不一致时报告 `DATA_CONFLICT`。每个状态文件由一个上传进程使用，恢复沿用同一文件、来源和目标。

状态字段为 `state`。全部暂存后，`unknown` 和 `cleanup_required` 重新调用 finish；`running` 读取进度；`failed` 报告错误码。仅在 `complete` 且返回引用与来源完全相同时写入输出文件。合并报告 `DATA_INCOMPLETE` 时清除本地“已完整暂存”标记，下次运行重新检查远程缺块。

stderr 输出 JSON 进度，包括本地准备、分块编码、请求耗时、复用块数、合并阶段和状态文件位置。请求耗时统计网络往返与远程处理的合计时间。状态和输出文件使用仅当前用户可读写权限。页面写入继续通过正常编辑流程提交。

上传完成后先读取目标页面，保留现有数据集元信息和指标定义，以最新 `expectedRevision` 提交 `put_dataset_ref`，再按常规编辑批次完成检查和发布。完整页面读取命令见 [MCP 完整配置下载](mcp-transport-diagnostics.md#完整配置下载)。

## COS 业务内容迁移与删除任务

本节用于需要将数据库业务行转成 COS 不可变包的项目维护。分享副本与作者资产使用独立前缀和引用。

工作区启用时先应用 `20261112020000_cos_assets.sql` 和 `20261112030000_cos_editor.sql`，再部署匹配版本的 Runtime。后一个迁移修复删除预览与确认的 SQL 变量引用，并让新建云端项目默认使用 `cos-v1`。原项目在显式迁移前仍使用 PostgreSQL 业务行；不能直接改格式标记来代替迁移。通过 `dataset_storage_inventory` 的 `cos.format` 检查实际格式，在线编辑接口返回的文档应包含 `storageFormat: "cos-v1"`。

新创建的 COS 数据包使用 Rust 从已校验的 SQLite 表生成 Parquet 行分片和单列候选项分片，保留 `query.sqlite3` 供服务器查询与缓存恢复。包描述新增 `dataFormat: "parquet-v1"`，沿用现有对象登记、数据版本与引用清理协议，不增加数据库迁移。原生程序或匹配的 UI 资源缺失时明确报错，不改写成 JSON 新包；服务器镜像已包含原生程序。旧包继续按原格式读取，元数据和版本声明仍使用 JSON。

配置分区字段时，Parquet 包保留分区到文件的索引和原始行序列，网页筛选仅下载匹配分片，跨分区明细与 CSV 仍按原行序输出。缺失字段与显式 null 分别保存。候选项可跨多个 Parquet 分片，读取旧包时仍兼容原 JSON 候选项索引。

迁移工具接收项目名和工作区根目录，凭据由运行环境提供。默认输出元数据清单，不上传或删除业务内容：

```sh
charts-design-runtime migrate-cos \
  --project <项目名> --workspace <工作区绝对路径>
```

预览清单后使用 `--apply` 执行。项目分片索引配置用于选择字符串或日期字段。工具复用已上传的数据包，检查数据校验值、上传分片行数、查询文件和配置内容；Parquet 分片下载并校验 SHA-256 后，再由原生程序实际解码核对字段与行数，候选项分片也逐片核验。仅在项目状态仍一致时原子切换指针。切换事务删除 PostgreSQL 中已迁移的业务分块；原草稿、检查点及发布配置改为 COS 引用。未完成分块没有可验证的数据版本时，必须先处理传输状态，不能直接清空。

迁移失败时保留源数据。新上传但尚未引用的对象保留在清单中，清理前检查其引用和迁移状态。全部切换后，重新加载兼容版本的服务进程以读取项目分片配置。回退时先完成反向数据迁移，再切换旧镜像。迁移期间暂停编辑；工具检查项目状态，并拒绝提交已经变化的快照。

历史版本删除由 `dashboard_version_delete_preview` 生成确认清单，再以返回的标识执行。最新、冻结及发布过的版本均可主动删除；关联多页面分享整体撤销。分享在最终登记成功后允许访问。上传与版本删除冲突时发布失败，暂存清理期限继续生效；“不过期”选项只在正式分享登记成功后生效。

删除任务保存在 PostgreSQL，先撤销访问，再删除 COS 对象的全部物理版本，最后清除业务行。失败任务可从版本中心继续清理。SCF 每 6 小时处理到期分享与失败删除任务，发布前继续要求最近 7 小时的成功清理记录。清理函数需要同一环境的 PostgreSQL 服务凭据及 COS 权限。函数仅在全部清理成功后更新成功心跳。部署后读取云端配置，确认告警和触发器的实际状态。

独立分享保持私有网关鉴权。新分享直接引用已有 Parquet COS 包；引用旧 JSON 包时，从其查询文件生成分享自己的 Parquet 行分片与候选项分片，保留原分区与行序，同一次多页分享按数据版本复用一次转换。旧数据包和既有分享不重写；不同新分享的旧数据转换文件各自持有，编码可复用本地缓存。到期清理只删除分享自身内容，不删除项目数据包。分享撤销阻止后续请求，不收回已经下载到浏览器的数据。物理数据清理以确认清单中的引用关系为准，不等同于数据库计费空间立即下降。
