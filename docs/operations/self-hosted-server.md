# 自托管服务器：远程 MCP 与网页预览

`bun bin/python-runtime.js -m dashboard_runtime server` 在一台服务器上同时提供远程 MCP（Streamable HTTP）和看板、分析报告的网页预览。它复用本地 Runtime 的同一套 `Service`、项目存储、Doctor 与前端构建；区别在于长期运行、按项目名隔离存储、用令牌和签名链接控制访问。本地 stdio MCP（`mcp` 命令）和本机编辑器（`serve` 命令）保持不变。

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
| `/s/<shareId>/` 及其资源 | 腾讯云独立只读副本 | 8 位数字密钥与受限会话 |

页面外壳不含业务数据；数据只经由带令牌的接口读取。分享令牌放在 URL 片段中，浏览器不会把片段发送给服务器、代理或 Referer；页面加载后从地址栏移除，只保留在当前标签页的 sessionStorage。

如果访问域名的提示页在跳转时丢失了 URL 片段，或链接令牌已失效，页面会提示粘贴收到的完整在线访问链接。输入内容只在当前页面读取；恢复时仅接受当前域名和路径对应的链接，并将其中的令牌保存在当前标签页。过期或已撤销的链接须重新签发。生产使用应配置稳定的正式域名，避免依赖测试域名提示页。

## 快速开始

基础服务器使用 MCP 可选依赖（含 Starlette 与 uvicorn），具体范围以 `pyproject.toml` 为准；腾讯云副本另需 cloud 依赖；Seaborn 统计图独立于旧 UI，需要另装 `.[statistics]`。

本机试用：

```sh
uv sync --locked --extra mcp --no-install-project
TOKEN=$(bun bin/python-runtime.js -c "import secrets;print(secrets.token_urlsafe(32))")
bun bin/python-runtime.js -m dashboard_runtime server --workspace ./charts-workspace --port 8000 --token "$TOKEN"
```

启动后打印 MCP 地址与管理入口。生产部署放在 HTTPS 反向代理之后，并设置对外地址：

```sh
bun bin/python-runtime.js -m dashboard_runtime server --workspace /data/projects --host 127.0.0.1 --port 8000 \
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

远程模式隐藏 `dashboard_export_open`（它会在服务器桌面上打开文件）；导出结果改为附带 `downloadUrl`，网页部署包另带 `siteDownloadUrl`。其余工具、操作合同、编辑批次与 Doctor 规则与本地相同，见 [Runtime 说明](../implementation/dashboard-runtime.md) 与 [项目资产与加载](../implementation/project-runtime.md)。

## 网页预览与分享

访问方式的名称见[看板交付术语](../agent/GLOSSARY.md)。在线链接连接服务端项目；腾讯云独立分享链接访问发布时生成的 COS 副本。

| 访问方式 | 创建方式 | 数据来源及更新 | 凭据与有效期 |
| --- | --- | --- | --- |
| 在线只读链接 | `dashboard_share`，`access=view` | 服务端项目的已保存检查点及其数据；CloudBase 存储在 PG，通过服务端 SQLite 缓存计算 | 链接包含访问令牌；按 `expiresInHours` 或服务器默认值过期，可撤销 |
| 在线编辑链接 | `dashboard_share`，`access=edit` | 同一服务端项目；支持网页提供的编辑、版本管理和恢复 | 同在线只读链接，权限包含网页支持的编辑操作 |
| 独立分享链接 | 正式发布后调用 `dashboard_share_publish` | 独立 COS 副本含发布时的网页和完整数据分片；浏览器加载后计算筛选等操作，项目更新不会自动更新该副本 | 8 位数字密钥；可选 7 天、30 天或不过期，可单独撤销 |

`dashboard_preview` 在支持 MCP Apps 的宿主中打开已保存检查点；需要浏览器链接时使用 `dashboard_share`。

- `dashboard_share`：`access` 为 `view`（只读）或 `edit`，`expiresInHours` 为 1–8784 小时。
- `dashboard_share_revoke`：使该看板此前签发的全部链接立即失效。
- 命令行：`bun bin/python-runtime.js -m dashboard_runtime share <项目> <看板> --workspace ... --public-url ... [--access edit] [--hours 24]`，只需能读取签名密钥。
- 管理入口 `/`：输入服务器令牌后列出项目与看板，点击生成 12 小时有效的预览或编辑链接。

| 权限 | 可用操作 |
| --- | --- |
| 只读链接 | 阅读看板或报告、筛选、表格分页与搜索、图表切换为表、查看指标定义与来源、导出文件、查看已有批注 |
| 编辑链接 | 另可拖动布局、修改标题与说明、编辑报告 Markdown、版本历史与恢复、运行诊断、生成网页部署包 |

签名链接默认只包含签发时的看板；调用 `dashboard_share` 时可通过 `dashboardIds` 指定同一项目的其他页面。页面切换只列出获准页面，访问其他页面返回 403。撤销其中任一页面的签名分享会使包含它的链接失效。导入数据、执行查询、新建看板等操作只通过 MCP 完成。报告在浏览器中按学术单栏排版，图表滚动到可见区域时加载。

页面以内容哈希引用 `app.<构建号>.js/css`，设置长期不可变缓存并以 gzip 压缩。响应头包含 CSP（仅允许本站脚本与经哈希固定的启动脚本）、`Referrer-Policy: no-referrer`、`X-Frame-Options: DENY`。

## 签名预览服务的边界

- 签名预览使用服务器令牌与签名链接；云端独立副本另用下节的数字密钥。没有用户账号、角色权限、行级权限或 OAuth。持有服务器令牌即可读写全部项目。
- 分享链接是持有即可用的凭据：转发链接等于转发权限。需要撤销时使用 `dashboard_share_revoke`，或更换签名密钥使全部链接失效。
- 查询能力仍只限运维方配置的只读 SQLite 别名；本地查询限制不是加固的多租户沙箱。
- 本地模式的 SQLite 使用 WAL，应使用同一主机上的持久磁盘，不能通过网络文件系统共享工作区。CloudBase 模式已接入 PostgreSQL 持久状态和 COS 文件存储，并使用无状态 MCP 会话；SQLite 仅保留为可重建的数据查询缓存。配置与查询边界见[项目存储](../implementation/project-runtime.md#存储)。
- 网页部署包（`dashboard_export_site`）仍是独立的只读静态站点，与本服务器互不依赖，见 [静态部署包](static-deployment.md)。

## 历史验收

2026-11-07 在 Linux 容器中验证：官方 MCP Python 客户端经 Streamable HTTP 完成工具列表、创建、越界路径拒绝、预览链接、导出下载与令牌鉴权；Chromium 打开只读与编辑链接，看板与报告图表正常渲染、无脚本或 CSP 错误，伪造令牌显示失效提示，手机宽度无横向溢出。自动测试见 `tests/runtime/test_server.py`。

2026-11-08，`main` 提交 `ae77261` 的 GitHub Actions 运行 40 六个作业全部通过，包含完整 Docker 多阶段构建、以非 root 用户运行镜像、远程 MCP、预览与下载冒烟检查。详细历史见[验收记录](../records/2026-11-07-server-layout-kpi.md)。

## 按版本自动发布到 CloudBase

GitHub Actions 工作流 `.github/workflows/cloudbase-release.yml` 监听 `vX.Y.Z` 标签。根目录 `package.json.version` 是云端发布号；Python 包的版本号独立维护。先提交需要上线的源码和工作流，再运行：

```sh
bun run release -- 1.2.1
```

替换为高于当前版本的新版本号。脚本要求工作区干净，更新 `package.json`，创建版本提交和附注标签，然后只推送该标签。其他改动须提前提交；脚本只推送标签，分支与原有全量测试流程保持原状。版本提交仍留在当前本地分支，后续按正常流程合并。加 `--dry-run` 只检查条件和展示步骤，不写文件或推送。

发布任务使用项目固定版本的 Bun 和固定版本的 CloudBase CLI。GitHub 运行发布脚本的局部测试，CloudBase 根据 `deploy/Dockerfile` 构建 React 与 Python 容器，并完成完整发布；不在本机重复构建。工作流中的并发组禁止打断正在执行的部署。推送标签须使用用户或发布机器的 Git 凭据，不使用另一个工作流的默认 `GITHUB_TOKEN`，以免无法触发后续工作流。

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

真实客户端需提供可访问上述 HTTPS 地址的目标环境，以及对应客户端的远程 MCP 配置入口。按每个目标客户端实际支持的请求头令牌或 URL 令牌方式连接，完成初始化、工具发现、在隔离项目中创建和修改合成看板、打开预览、下载导出、撤销链接与重新连接。Codex、Claude Desktop、Claude Code、claude.ai 的兼容性分别记录，不用官方 Python SDK 的通过结果代替。未实现 OAuth，必须先确认目标客户端支持当前令牌接入方式；只支持 OAuth 的入口不在现有能力内。

## 腾讯云在线分享与云端清理

状态：COS、HTTPS 网关和 SCF 已部署；目标清理周期为每 6 小时，部署前应先更新网关的清理状态检查，再更新云端触发器。候选版本的密钥访问与撤销已通过云端验收。部署与物理删除结果记录在[部署方案](../plans/cloud-hosting-and-version-control.md)。

腾讯云分享保存一份独立、只读的看板或分析报告副本，也可以将同一项目中选定的多个页面打包到同一链接。网页、运行资源、使用中的完整数据集分片和访问控制记录保存在私有 COS。访客通过 HTTPS 网关访问，输入 8 位数字访问密钥后阅读；浏览器不会获得公开 COS 地址。

清理任务由腾讯云 SCF 定时触发执行，不由本地 MCP、用户电脑或网页网关进程执行。删除范围包括该分享副本的对象历史版本、删除标记、密钥哈希与清理任务记录。本地项目原稿和其他分享副本保留。

### MCP 操作

先完成编辑批次，再用最新版本发布：

1. `dashboard_get` 读取草稿与版本。
2. 有修改时按 `dashboard_edit_begin` → 修改 → `dashboard_edit_finish` 完成检查点；用 `dashboard_version_publish` 将选定已保存版本设为正式发布版本。
3. 调用 `dashboard_share_publish`，传入相同的 `projectRoot`、`dashboardId`；`expectedRevision` 使用当前 `publishedRevision`。可通过 `pages` 指定其他页面及其当前正式发布版本，每页都需先发布。草稿可以比发布版本更新。
4. 将返回的 `accessUrl` 交给指定读者，打开后自动填入密钥，再点击“打开分享”；也可分别发送 `url` 和 `accessKey`。

| 参数 | 说明 |
| --- | --- |
| `expiration` | `never` 不过期；`7d` 七天后过期，默认值；`30d` 三十天后过期。时间从发布时开始计算 |
| `accessKey` | 可选，必须是 8 位 ASCII 数字字符串，可包含前导零；省略时随机生成 |
| `expectedRevision` | 项目模式下必须等于当前正式发布版本，防止误分享未发布草稿 |

返回 `shareId`、`url`、`accessUrl`、`accessKey`、`revision`、`expiration`、`expiresAt` 和 `cleanupExecutor`。`expiresAt` 是 UTC Unix 秒数，不过期时为 `null`；`cleanupExecutor` 为 `tencent-scf`。分享路径使用随机十六进制标识。

`url` 不含密钥；`accessUrl` 使用 `url#key=访问密钥`，浏览器读取片段后自动填入并从地址栏移除。片段不发送给服务器；表单仍通过 HTTPS POST 校验密钥。带密钥链接只在新建或替换分享时返回；COS 控制记录和状态接口只保留不含密钥的信息。已有 `url` 可由持有者在本机追加同样的片段使用。

登录页采用居中表单，支持窄屏和键盘操作。表单响应使用 `Referrer-Policy: same-origin`，避免浏览器在 `no-referrer` 下将 POST 来源置为 `null`；服务器继续拒绝 `null` 和其他站点的 Origin。样式及自动填入脚本使用随机 CSP nonce，来源错误和密钥错误均显示在表单内。

`dashboard_share_status` 查询本项目、本看板的分享任务，可传入一个 `shareId`。它不返回访问密钥。响应不确定时先查询，再决定是否重发。

`dashboard_share_replace` 将选定分享替换为当前正式发布版本：先完成新副本上传，再撤销旧分享，返回新链接和新密钥；多页面分享替换时保留页面范围，并使用各页面当前正式发布版本。其他分享不受影响。若 `previousRevoked=false`，保留返回的新凭据，并按 `followUp` 撤销旧分享。

`dashboard_share_delete` 撤销一个 `shareId`，立即阻止访问，并将物理删除交给 SCF。`cleanupState=pending` 表示等待清理或重试。清理完成后，该任务从状态列表消失。此操作也适用于不过期分享。

原 `dashboard_share` 和 `dashboard_share_revoke` 继续用于自托管服务的签名预览链接；它们不创建或删除 COS 分享副本。

### 云端组成

| 组成 | 职责 |
| --- | --- |
| HTTPS 网关 | 将现有自托管服务器部署在云端；提供 `/s/<shareId>/` 密钥表单、会话和逐文件鉴权。每次请求都检查到期时间 |
| 私有 COS | 保存独立网页与数据；对象不公开，响应设置 `no-store` |
| SCF 云函数 | 每 6 小时扫描清理任务；删除到期、撤销或中断上传的副本；删除失败保留任务并使函数调用失败，后续触发继续重试 |

密钥会话使用 `Secure`、`HttpOnly`、`SameSite=Strict` Cookie。密钥输入有按分享和访客计数的尝试限制。网页资源、Worker 和数据分片均通过网关读取，不能绕过密钥直接访问。

到期即拒绝新的云端读取。SCF 每 6 小时触发，正常情况下物理删除需等待最多一个周期，额外耗时由数据量和云端请求决定；失败后在下一个周期重试。清理覆盖当前对象、所有历史版本和删除标记；任何批次删除失败都不能将任务标记为完成。

新发布前会检查 SCF 最近 7 小时内是否完成过一次成功清理，为 6 小时触发周期保留 1 小时余量。没有有效清理状态时返回 `CLOUD_CLEANER_UNAVAILABLE`，不会上传新副本。上传开始前先保存清理任务；中断的上传一小时后进入待清理状态，等待下次 SCF 执行。发布过程使用操作系统临时目录，上传结束或失败后删除，兼容 macOS 与 Linux 容器。

### 配置

部署环境使用通用环境变量。COS 支持执行角色注入的临时凭据；设置 `CHARTS_COS_AUTH=cloudbase` 时使用服务端 CloudBase API Key 换取临时凭据，并在运行期间刷新。网页中不包含云凭据。

| 环境变量 | 网关/发布进程 | SCF |
| --- | --- | --- |
| `CHARTS_PUBLIC_URL` | 必填，已部署网关的 HTTPS 地址，可含路径前缀 | 不需要 |
| `CHARTS_COS_REGION` | 必填，COS 地域 | 必填，同一地域 |
| `CHARTS_COS_BUCKET` | 必填，专用于分享的私有存储桶 | 必填，同一存储桶 |
| `CHARTS_COS_SHARE_PREFIX` | 默认 `charts-shares/`，非空独立前缀 | 必须与发布进程相同 |
| `TENCENTCLOUD_SECRETID`、`TENCENTCLOUD_SECRETKEY`、`TENCENTCLOUD_SESSIONTOKEN` | 执行角色方式下由环境提供；临时凭据需包含 Token | 执行角色方式下每次调用重新读取 |
| `CHARTS_COS_AUTH=cloudbase`、`CLOUDBASE_ENV_ID`、`CLOUDBASE_API_KEY` | 使用服务端环境密钥换取并刷新 COS 临时凭据 | 当前部署使用同一方式，不依赖本地进程 |

从本仓安装发布进程：`uv sync --locked --extra mcp --extra cloud --no-install-project`。自托管 Docker 镜像包含 COS SDK。

存储桶必须私有；禁止匿名访问，分享前缀禁用额外复制、备份和 CDN 缓存。发布前检查桶 ACL 和匿名访问策略。桶权限由部署人员配置；清理程序删除配置存储桶中的分享对象。

### 部署 SCF 定时任务

源码位于 `deploy/tencent-cleaner/`。从项目根目录构建 Linux x86_64 函数包：

```sh
docker buildx build --platform linux/amd64 \
  -f deploy/tencent-cleaner/Dockerfile \
  --output type=local,dest=/private/tmp/charts-cleaner-package .
```

将生成的 `/private/tmp/charts-cleaner-package/cleaner.zip` 部署为 SCF 事件函数：

- 运行环境：Python 3.10，x86_64；入口：`index.main_handler`。
- 配置上表中的 COS 地域、桶和前缀。
- 采用已有执行角色或 `CHARTS_COS_AUTH=cloudbase` 服务端凭据方式。执行角色权限应限于分享前缀：列举当前对象和历史版本、读取清理任务、删除对象及其历史版本、写入 `cleaner-status.json`。函数不创建或扩大角色权限。
- 添加定时触发器。使用 `deploy/tencent-cleaner/timer.json`，Cron 为 `0 0 */6 * * * *`，每 6 小时一次，并启用触发器。已有部署应先发布支持 7 小时状态有效期的网关，再更新触发器。
- 开启函数失败告警。部分删除失败时函数抛错，任务继续保留，下一次定时触发重试。
- 等待首次成功调用，再发布分享。发布工具会检查云函数保存的清理状态。

函数入口要求 `TENCENTCLOUD_RUNENV=SCF`；本地直接执行会拒绝运行。网关和 MCP 中没有清理轮询，也不需要本地进程保持在线。

### 检查边界

后端局部检查覆盖密钥访问、每个文件的鉴权、七天/三十天到期、不过期、主动撤销、物理版本删除、清理失败重试、SCF 环境限制，以及保留原稿和其他副本。

上线时须在目标账号验证一次发布、密钥访问、到期删除和重试，并确认云端触发器在本地进程退出后仍执行。

维护时机：服务器配置、鉴权、分享、存储或云端清理方式改变时更新；历史验收结论不替代目标部署确认。

### 从本地项目迁移选定数据

云端迁移使用 `dataset_transfer_chunk`、`dataset_transfer_finish`、`dataset_transfer_status` 和 `dataset_transfer_cleanup`。每个数据版本分成最多 250 行、JSON 不超过 2 MiB 的批次；相同传输 ID 和批次重试时内容必须一致。批次先放在私有 COS，服务端重算原始数据版本并持久保存后才可引用：未切换项目写入 PostgreSQL 业务分块，`cos-v1` 项目生成 COS 数据包并登记 PostgreSQL 元信息。完成后删除该传输的 COS 暂存对象及历史版本。中断可继续；主动放弃时调用 `dataset_transfer_cleanup` 指定该传输 ID。服务重启后状态可能为 `unknown`，重新调用 `dataset_transfer_finish`；返回 `cleanup_required` 也重新调用 finish 完成清理。迁移需要现有服务凭据对分享桶执行读取、写入、列举对象版本和删除该暂存前缀的权限；不会自动更改权限。

`bin/transfer-project.py` 从用户审核的清单读取本地草稿与选定数据集，通过上述 MCP 工具顺序传输。清单包含本地 `projectRoot`，每页的 `dashboardId`、`draftRevision`、`componentCount`，以及每个选定数据集的 `id`、`version`、`rowCount`、`bytes`。脚本拒绝版本变化或清单缺少组件绑定的数据，保留组件、筛选、选定数据集的全部指标与批注；其他未选数据集及其指标不进入迁移副本。相同数据版本只传输一次。它创建新页面，不覆盖不同内容的现有页面；目标页面的版本从 1 开始，本地历史不会迁入。来源执行认证状态会标为 supplied。

通过项目 1Password 入口注入 `CHARTS_SERVER_TOKENS`，脚本使用列表中的第一个令牌；`CHARTS_MCP_URL` 是 HTTPS MCP 地址。不要将令牌值写入命令、文件或仓库。项目入口会切换到登记的项目目录，运行前切换到需要使用的源码目录。使用专门的状态文件记录可续传 ID，不包含令牌：

```sh
project-run <项目目录名> -- /bin/sh -c '
  cd /absolute/path/charts-design
  export CHARTS_MCP_URL="$(gh variable get CLOUDBASE_SERVICE_URL)/mcp"
  bun run python -- bin/transfer-project.py \
    --manifest /absolute/path/online-migration-manifest.json \
    --project <远程项目名> --state /private/tmp/charts-transfer-state.json
'
```

迁移成功只表示创建了页面，须对每页运行 `dashboard_checkpoint`（内含完整 Doctor）并确认通过，再运行 `dashboard_version_publish`；之后才能通过 `dashboard_share_publish.pages` 创建多页分享。传输中止或清理失败时保留状态文件并使用相同参数重试；不要删除该文件后盲目重传。用户决定放弃时，从状态文件的 `uploads` 中取得对应 ID，调用 `dataset_transfer_cleanup`，并确认成功。不会自动清理无人恢复的中断传输。

合并时，`dataset_transfer_status` 的 `phase` 标明读取暂存分块、保存数据库分块或清理；`completed` 和 `total` 对应当前阶段。脚本会记录已完整暂存的版本，恢复时不再发送这些数据行。使用旧版脚本时，只有在已确认某个版本全部分块均已暂存的情况下，才在恢复命令中加 `--resume-staged <完整数据版本号>`；缺块时合并报错，不会创建不完整的数据版本。

## COS 业务内容迁移与删除任务

上线时先应用 `20261112020000_cos_assets.sql`，再部署兼容版本的 Runtime，使删除按钮和确认接口同时生效。原项目在显式迁移前仍使用 PostgreSQL 业务行；项目切换状态由迁移记录确认。

迁移工具接收项目名和工作区根目录，凭据由运行环境提供。默认输出元数据清单，不上传或删除业务内容：

```sh
bun run python -- -m dashboard_runtime.cos_migrate \
  --project <项目名> --workspace <工作区绝对路径>
```

明确安排迁移后才能加 `--apply`。可重复传入 `--partition-field <字段名>`，将匹配的字符串或日期字段保存为项目分片索引配置。工具复用已上传的数据包，检查数据校验值、上传分片行数、查询文件和配置内容，并在项目状态仍一致时原子切换指针。切换事务删除 PostgreSQL 中已迁移的业务分块；原草稿、检查点及发布配置改为 COS 引用。未完成分块没有可验证的数据版本时，必须先处理传输状态，不能直接清空。

迁移失败时保留源数据。新上传但尚未引用的对象保留在清单中，清理前检查其引用和迁移状态。全部切换后，重新加载兼容版本的服务进程以读取项目分片配置。回退时先完成反向数据迁移，再切换旧镜像。迁移期间暂停编辑；工具检查项目状态，并拒绝提交已经变化的快照。

历史版本删除由 `dashboard_version_delete_preview` 生成确认清单，再以返回的标识执行。最新、冻结及发布过的版本均可主动删除；关联多页面分享整体撤销。分享在最终登记成功后允许访问。上传与版本删除冲突时发布失败，暂存清理期限继续生效；“不过期”选项只在正式分享登记成功后生效。

删除任务保存在 PostgreSQL，先撤销访问，再删除 COS 对象的全部物理版本，最后清除业务行。失败任务可从版本中心继续清理。SCF 每 6 小时处理到期分享与失败删除任务，发布前继续要求最近 7 小时的成功清理记录。清理函数需要同一环境的 PostgreSQL 服务凭据及 COS 权限。函数仅在全部清理成功后更新成功心跳。部署后读取云端配置，确认告警和触发器的实际状态。

独立分享保持私有网关鉴权，新分享的数据文件引用统一 COS 包；到期清理只删除分享自身内容，不删除项目数据包。分享撤销阻止后续请求，不收回已经下载到浏览器的数据。物理数据清理以确认清单中的引用关系为准，不等同于数据库计费空间立即下降。
