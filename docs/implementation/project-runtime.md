# 项目资产与渐进加载

## 存储

默认 `CHARTS_STORAGE_BACKEND=local`，保留下面的 SQLite 和本地文件行为。

`CHARTS_STORAGE_BACKEND=cloudbase` 使用 `CloudProjectStore`，以服务端 `CLOUDBASE_ENV_ID` 和 `CLOUDBASE_API_KEY` 调用 PostgreSQL HTTP RPC；适用于没有 TCP 直连入口的共享 PostgreSQL。先通过 CLI 应用 `cloudbase/migrations/` 中的迁移。RPC 在函数内部检查 `service_role`，不能只依赖函数执行授权；客户端和网页仍使用 MCP 自己的访问令牌。

云端存储按项目记录 `storageFormat`。尚未迁移的项目继续将完整配置和业务行分块保存在 PostgreSQL；`cos-v1` 项目把业务行、配置快照、首页计算结果和统计图产物保存在私有 COS。PostgreSQL 保留草稿与版本指针、数据元信息、批注、编辑批次、权限与分享状态、对象登记及删除任务。变更继续在项目级事务中检查修订号和批注状态。

`cloud_assets.py` 保存不可变对象包，每次上传使用新的对象代次。同项目的可用数据版本复用已有对象包；包包含每片最多 5,000 行的压缩 JSON、独立字段选项索引、内容校验值及预生成 SQLite 查询文件。项目可配置 `storage.partitionFields`；使用第一个匹配的字符串或日期字段，按字段值实际分片并建立索引，网页只读取所需分片，再对实际行执行筛选。分区文件同时保存原始行号，浏览器合并后恢复原始行序。没有可用分区条件时读取所需数据集的全部分片，不抽样。

网页编辑、在线只读、历史预览和新的独立分享复用同一查询 worker。鉴权网关转发 COS 字节，普通网页筛选不调用 PostgreSQL 业务行查询。MCP 保留服务端 SQLite 查询语义，冷实例下载对应对象代次的查询文件并直接打开，不再逐块恢复业务行。查询文件、数据分片和字段索引会增加 COS 持久存储；实际时长、流量与费用变化仍需另行测量。

配置保存先写 COS，再提交 PostgreSQL 指针；未被提交引用的上传包仍登记在对象清单，不能按年龄推断为可删除业务内容。未迁移项目仍使用原分块恢复路径。迁移和回退边界见[自托管服务器](../operations/self-hosted-server.md#cos-业务内容迁移与删除任务)。

远程导出下载使用 COS 保存字节、PostgreSQL 保存文件引用；签名下载在新实例上可恢复文件。`CHARTS_COS_ASSET_PREFIX` 默认为 `charts-assets/`，不能与可过期分享的 `CHARTS_COS_SHARE_PREFIX` 重叠。项目资产不参与分享过期清理。本地 JSON 镜像不作为云端状态源。

项目内 `charts-project.json` 管理历史和加载参数；`dashboards/dashboards.sqlite3` 是事务索引与权威状态，`dashboards/<id>/draft.json`、`checkpoints/*.json`、`annotations.json` 和 `annotation-history.json` 是自动生成的可读镜像，不能另行手工维护。检查点写入后不再变化，其镜像只在首次出现时写出；迁移改写检查点时整体重写镜像。`data/data.sqlite3` 保存不可变数据版本。运行目录仅用于传输缓存及诊断；删除新运行缓存不删除项目资产。既有集中目录不自动清理。

项目默认配置由 `dashboard_runtime/project.py` 的 `DEFAULTS` 维护。`loading.pageSize` 是后端未显式提供表格状态时的缺省值，不等同于 UI 明确传入的表格页大小。保存版本固定内容；命名及旧 published 保留标记不阻止用户主动删除。项目检查点不再随保存隐式裁剪。设计 JSON 和业务数据不应作为公共仓库产物提交。

## 保存、发布与恢复

项目草稿、已保存检查点与正式发布版本分别记录。`dashboard_checkpoint`／`dashboard_edit_finish` 保存检查点；`dashboard_version_publish` 选择一个已保存版本作为正式发布版本，重复发布当前版本不会重复写入发布事件。`dashboard_version_status` 返回三种修订号和发布记录，`dashboard_version_get` 只读查看保存或发布过的内容。

`dashboard_restore` 生成新草稿并保留现有批注；保存检查点和更改正式发布需另行执行。检查点中的旧 `published` 字段表示历史保留保护；正式发布状态由发布记录确定。发布记录保存不可变内容与数据引用，检查点清理后仍可查看和回退到发布过的版本。

共享编辑器在“版本与分享”侧栏提供保存、完整只读历史预览、恢复为草稿、发布记录和独立分享。历史预览使用独立查看状态，切换不改变草稿或发布指针。未保存布局和标题在打开版本中心前提供保存、放弃、取消三个选择。COS 历史预览使用同一网页读取器，未迁移项目通过固定版本的查询接口分页计算，预览响应仅包含该页结果。

替换选定分享会先生成新链接和不同的新密钥，再撤销旧链接与旧会话；其他独立分享保留。若新副本上传失败，旧分享保留；若新副本成功但旧分享撤销失败，操作返回新凭据与明确的待撤销状态，只重试撤销旧分享。

## 单入口多项目

报表资产归属于项目，但 MCP 进程不需要固定绑定一个项目。统一入口不带 `--project-root`；在包根目录启动：

```sh
bun bin/dashboard-runtime.js --runtime-root "$HOME/.cache/charts-design" mcp
```

每次项目工具调用都传 `projectRoot`，值是报表资产目录的绝对路径，不是 Agent 工作目录。示例：

```json
{"projectRoot":"/Users/w/code/analyst-workspace/project/domestic-transfer-analysis","dashboardId":"domestic-transfer-analysis-20261019"}
```

相同 `dashboardId` 可存在于不同项目。所有工具，包括 `dashboard_list`、`runtime_info`、分块读取、诊断、编辑、历史和数据导出，都支持该参数。项目路径会规范为绝对真实路径；相对路径和空值被拒绝。首次明确访问新目录时沿用 `ProjectStore` 创建项目资产结构。不提供项目目录枚举、自动发现或跨项目聚合。

每个项目使用固定的 `Service` 和资产目录；运行缓存保存在统一运行目录的 `projects/<项目路径标识>/` 下。不存在“当前项目”，一次调用不会改变下一次调用的项目。传输分块与诊断同样按项目隔离，重启后可用原项目参数继续读取尚未过期的分块。数据源别名继续由启动时的 `--sources` 配置，不允许工具请求另设数据源配置。

### 自托管服务器中的项目

`server` 命令以一个工作区目录承载全部项目。远程调用的 `projectRoot` 是项目名（字母、数字、`-`、`_`），对应 `<workspace>/<项目名>/`，目录结构与本地项目相同；运行缓存在 `<workspace>/.runtime/projects/<项目名>/`。工作区直接子目录的绝对路径也被接受，其他路径以 `PROJECT_OUTSIDE_WORKSPACE` 拒绝。结果中的 `projectRoot` 返回项目名。部署、令牌与分享链接见 [自托管服务器](../operations/self-hosted-server.md)。

### 兼容与 Router

- 原 `--project-root <project> --runtime-root <runtime> mcp` 保留为启动默认项目。不传 `projectRoot` 时仍访问原项目和原运行目录；传入另一个项目时只影响该次调用，不需要迁移已有资产。
- 原 `--root` 集中存储仍可读取。不带启动默认项目且请求省略 `projectRoot` 时，只访问该旧存储，不沿用最近一次项目选择；新建看板需明确项目。CLI 与本地 HTTP 编辑器继续使用启动时选择的存储，本节多项目请求分发针对 MCP。
- 可经 Magpie MCP router 转发，仍使用标准 stdio MCP，无需为项目分别注册。Router 必须保留每次工具调用的 `projectRoot`、结构化结果、`_meta.ui.resourceUri`、资源读取与 MCP Apps 的后续工具路由；不能只转发首次预览。若 Router 改写工具名，必须把页面后续调用映射回同一后端。

## 编辑与展示

`dashboard_edit_begin` 开始或恢复批次；`dashboard_patch` 只保存草稿并发编号。`dashboard_edit_finish` 完整检查后生成一个检查点，成功返回 `nextAction: dashboard_preview`。调用方只在完成后调用一次预览。已有页面通过版本检测原位更新；宿主是否复用打开的侧栏由宿主控制。

`dashboard_get` 读取可编辑草稿；项目预览与刷新读取最近完成的检查点。`dashboard_edit_finish` 和 `dashboard_checkpoint` 检查失败时返回 `DOCTOR_FAILED`，MCP 同时标记 `isError: true`；草稿与批次保留，不生成检查点。调用方检查 Doctor 问题、读取最新草稿并修复，再用最新版本完成。`REVISION_CONFLICT` 要求重新读取并合并当前修改，不能盲目重放写入。

`dashboard_history` 分页读取检查点，默认每页 50 个、最多 100 个；`dashboard_history_diff` 比较；`dashboard_checkpoint` 创建或命名当前检查点，也会关闭当前编辑批次，普通 Agent 编辑使用带批次 ID 的 `dashboard_edit_finish`。`published` 保护检查点免于自动清理。`dashboard_restore` 默认恢复设计及对应数据引用，可用 `useCurrentData` 明确保留当前数据。批注独立保存，批注变更保存在独立事件记录。

版本列表允许删除最新、当前发布、曾发布及带保留标记的版本。`dashboard_version_delete_preview` 生成一次确认清单，包含将撤销的完整分享、专属 COS 对象、PostgreSQL 内容估算及保留引用。`dashboard_version_delete` 必须携带确认标识；项目状态变化或清单超过 15 分钟时重新确认。批注及其历史的数据引用采用保守匹配，无法排除引用的数据不删除。

删除先在事务中撤销关联分享、移除历史内容及标记专属对象，再立即清除 COS 对象的所有物理版本，最后删除无引用的 PostgreSQL 业务分块。失败保留任务并显示“访问已撤销，文件清理未完成”；可手动重试或由 SCF 继续清理。删除当前发布版本清空发布指针，不自动发布旧版本；在线只读使用剩余最新检查点，全部删除后返回“暂无已保存版本”。当前草稿保留；如其编号等于被删除版本，推进草稿修订号以避免复用已删除编号。

本地项目采用同样的确认入口，删除检查点、发布内容及镜像，数据资产保留并在清单说明。COS 和 PostgreSQL 物理清理针对 CloudBase 项目。

`dataset_storage_inventory` 保留原数据版本引用盘点，并增加 COS 对象登记、包体积及项目迁移状态。盘点输出元数据。数据库计费空间以平台后续统计为准。`charts_delete_checkpoint` RPC 同样要求执行新的确认流程。

## 加载

项目模式预览返回结构和数据版本，不返回全组件计算结果。页面按可见组件调用 `dashboard_view`，使用 `componentIds`、`responseMode: patch`、`expectedRevision`、`dataVersion`、`filterSequence`。请求按最新筛选代次更新；旧响应不覆盖当前筛选。表格分页和筛选选项独立查询。临时点击下钻不持久化为设计版本。

## 诊断

`dashboard_doctor` 的 quick/full 模式检查定义、数据引用与组件计算。结果带请求编号，设计、数据和 UI 版本。完整批次检查失败不生成检查点。`runtime_diagnostics` 支持看板、请求编号、阶段及错误码过滤。页面提供运行诊断入口。

## 迁移

`--project-root <destination> --runtime-root <cache> migrate-project --source-root <legacy> --board <id>` 先列清单；加 `--apply` 才迁移。只复制选中看板及其历史引用的数据版本，流式核对数据引用，保留历史编号和批注事件；不删除源数据。目标已有同名看板时拒绝覆盖。

## 筛选性能

`loading.preloadFilterIds` 指定需要随结构返回首页选项的筛选器；每项最多100个值，高基数选项继续搜索分页。选项范围不随当前选择收缩，避免改变筛选语义。预加载结果缓存在运行目录 `filter-options/`，键包含字段和关联数据版本，删除后可重建。

页面以看板、数据版本、字段、数据集、搜索词和页号缓存筛选页，并复用进行中的相同请求；缓存最多256页。失败请求不缓存。大响应最多同时读取4个分块，仍校验顺序、完整字节数和JSON；不截断、抽样或丢弃图表数据。选项接口耗时现在可以在 `runtime_diagnostics` 的 `query_complete` 阶段查询。

## 本地数据计算

复用 stdio MCP 进程和本机 SQLite，无需启动 HTTP 服务或增加常驻进程。完整数据保存在 `data.sqlite3`；看板配置及历史只保存不可变版本引用。指标卡与图表读取聚合结果，表格只读取当前页；筛选、排序、分页和全量 CSV 导出在本机执行。比例使用分子合计除以分母合计。

使用配置好的只读 SQLite 来源别名调用 `dataset_attach`；用 `dashboard_view` 读取交互结果，`dashboard_data_inspect` 检查行数、体积与耗时，`dataset_export` 导出全部匹配行。高基数筛选选项可搜索并逐页加载，超出聚合结果上限明确报错，不截断数据。标题与布局修改复用原数据版本。

旧快照可调用 `dashboard_migrate`，先生成备份再迁移全部配置历史；`dashboard_migration_rollback` 将备份恢复为新修订。小数据保留旧快照兼容。详细契约和复测命令见 [local-data.md](../../skills/executive-charts/references/local-data.md)。本地 AppBridge 验证与真实 Codex 宿主验证分别记录，不互相替代。

## 局部视图与明细接口

`dashboard_view` 默认返回完整 `document`。交互调用可传 `responseMode: "patch"`、`componentIds` 和 `expectedRevision`，返回 `{id, revision, componentIds, computed, statisticalArtifacts}`。`computed.components`、`tables`、`grouped` 只包含选中的组件；省略字段表示保留已有值，空数组表示清空。省略 `componentIds` 表示全部，空列表表示不计算组件。仅在需要重新加载筛选选项时传 `includeFilterOptions: true`。版本不符返回 `REVISION_CONFLICT`；先刷新最新定义再重试。MCP 结构化结果与文本回退返回相同的小结果；超过阈值时均返回分块描述，消费者读取完整分块。不得把摘要或截断文本当完整响应，详细协议见传输与诊断文档。

`component_data` 接受 `sort: [{field, direction}]` 与 `search`，沿用表格排序和子串搜索规则。指标定义面板展示 `semantic_inspect` 返回的实际结果。图表转表显示对应完整聚合结果，并在自身容器内滚动。主表默认每页 10 行，明确配置继续保留；搜索、排序、分页由后端执行。CSV 导出全部匹配行，HTML 快照保留当前计算视图。

本项目 MCP 中，有数据集绑定的组件在详情面板底部显示“明细数据”，打开面板后通过 `component_data` 读取当前筛选范围内的原始行，并携带当前版本检查。每页默认 10 行，搜索、排序和翻页在后端执行；明细的表格状态独立于看板主表，关闭面板后丢弃。来源与原始定义折叠区保留在明细之后。静态快照、无数据集绑定的组件不调用此接口。

## 独立性能测量

百万行本地数据的独立合成验收：

```sh
bun bin/python-runtime.js tests/runtime/benchmark_local.py --rows 1000000 --output /private/tmp/charts-performance.json
```

该命令创建独立临时 SQLite 数据，以两张指标卡、一个分类图和一张明细表检查导入、打开、筛选、聚合、翻页、排序、搜索和完整 CSV 导出，并记录响应体积、进程峰值内存及磁盘大小。结果核对独立计算的行数与合计，测量范围为后端查询和数据导出。首次全字段子串搜索需扫描完整数据；自然字符串排序、多列排序及随机深页使用 OFFSET。缓存绑定不可变数据版本。

维护时机：项目选择、持久化、编辑历史、数据版本或渐进查询行为改变时更新；当次测量结果保存为独立证据。
