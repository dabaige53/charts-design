# 项目资产与渐进加载

## 存储

项目内 `charts-project.json` 管理历史和加载参数；`dashboards/dashboards.sqlite3` 是事务索引与权威状态，`dashboards/<id>/draft.json`、`checkpoints/*.json`、`annotations.json` 和 `annotation-history.json` 是自动生成的可读镜像，不能另行手工维护。检查点写入后不再变化，其镜像只在首次出现时写出；迁移改写检查点时整体重写镜像。`data/data.sqlite3` 保存不可变数据版本。运行目录仅用于传输缓存及诊断；删除新运行缓存不删除项目资产。既有集中目录不自动清理。

项目默认配置：普通检查点保留100个，筛选合并150毫秒，最多4个组件查询并发，表格50行。命名和发布检查点保护。数据不自动清理，避免删除仍被历史或批注引用的数据。设计JSON和数据内容不应作为含敏感数据的公共仓库产物提交。

## 单入口多项目

报表资产归属于项目，但 MCP 进程不需要固定绑定一个项目。统一入口不带 `--project-root`；在包根目录启动：

```sh
node bin/dashboard-runtime.js --runtime-root "$HOME/.cache/charts-design" mcp
```


每次项目工具调用都传 `projectRoot`，值是报表资产目录的绝对路径，不是 Agent 工作目录。示例：

```json
{"projectRoot":"/Users/w/code/analyst-workspace/project/domestic-transfer-analysis","dashboardId":"domestic-transfer-analysis-20261019"}
```

相同 `dashboardId` 可存在于不同项目。所有工具，包括 `dashboard_list`、`runtime_info`、分块读取、诊断、编辑、历史和数据导出，都支持该参数。项目路径会规范为绝对真实路径；相对路径和空值被拒绝。首次明确访问新目录时沿用 `ProjectStore` 创建项目资产结构。不提供项目目录枚举、自动发现或跨项目聚合。

每个项目使用固定的 `Service` 和资产目录；运行缓存保存在统一运行目录的 `projects/<项目路径标识>/` 下。不存在“当前项目”，一次调用不会改变下一次调用的项目。传输分块与诊断同样按项目隔离，重启后可用原项目参数继续读取尚未过期的分块。数据源别名继续由启动时的 `--sources` 配置，不允许工具请求另设数据源配置。


### 自托管服务器中的项目

`server` 命令以一个工作区目录承载全部项目。远程调用的 `projectRoot` 是项目名（字母、数字、`-`、`_`），对应 `<workspace>/<项目名>/`，目录结构与本地项目相同；运行缓存在 `<workspace>/.runtime/projects/<项目名>/`。工作区直接子目录的绝对路径也被接受，其他路径以 `PROJECT_OUTSIDE_WORKSPACE` 拒绝。结果中的 `projectRoot` 返回项目名。部署、令牌与分享链接见 [自托管服务器](self-hosted-server.md)。

### 兼容与 Router

- 原 `--project-root <project> --runtime-root <runtime> mcp` 保留为启动默认项目。不传 `projectRoot` 时仍访问原项目和原运行目录；传入另一个项目时只影响该次调用，不需要迁移已有资产。
- 原 `--root` 集中存储仍可读取。不带启动默认项目且请求省略 `projectRoot` 时，只访问该旧存储，不沿用最近一次项目选择；新建看板需明确项目。CLI 与本地 HTTP 编辑器继续使用启动时选择的存储，本节多项目请求分发针对 MCP。
- 可经 Magpie MCP router 转发，仍使用标准 stdio MCP，无需为项目分别注册。Router 必须保留每次工具调用的 `projectRoot`、结构化结果、`_meta.ui.resourceUri`、资源读取与 MCP Apps 的后续工具路由；不能只转发首次预览。若 Router 改写工具名，必须把页面后续调用映射回同一后端。

## 编辑与展示

`dashboard_edit_begin` 开始或恢复批次；`dashboard_patch` 只保存草稿并发编号。`dashboard_edit_finish` 完整检查后生成一个检查点，成功返回 `nextAction: dashboard_preview`。调用方只在完成后调用一次预览。已有页面通过版本检测原位更新；宿主是否复用打开的侧栏由宿主控制。

`dashboard_history` 分页读取检查点；`dashboard_history_diff` 比较；`dashboard_checkpoint` 创建、命名或标记发布当前检查点；`dashboard_restore` 默认恢复设计及对应数据引用，可用 `useCurrentData` 明确保留当前数据。批注独立保存，不随设计恢复。历史文档中的批注变更保存在独立事件记录。

## 加载

项目模式预览返回结构和数据版本，不返回全组件计算结果。页面按可见组件调用 `dashboard_view`，使用 `componentIds`、`responseMode: patch`、`expectedRevision`、`dataVersion`、`filterSequence`。请求按最新筛选代次更新；旧响应不覆盖当前筛选。表格分页和筛选选项独立查询。临时点击下钻不持久化为设计版本。

## 诊断

`dashboard_doctor` 的 quick/full 模式检查定义、数据引用与组件计算。结果带请求编号，设计、数据和 UI 版本。完整批次检查失败不生成检查点。`runtime_diagnostics` 支持看板、请求编号、阶段及错误码过滤。页面提供运行诊断入口。

## 迁移

`--project-root <destination> --runtime-root <cache> migrate-project --source-root <legacy> --board <id>` 先列清单；加 `--apply` 才迁移。只复制选中看板及其历史引用的数据版本，流式核对数据引用，保留历史编号和批注事件；不删除源数据。目标已有同名看板时拒绝覆盖。

## 筛选性能

`loading.preloadFilterIds` 指定需要随结构返回首页选项的筛选器；每项最多100个值，高基数选项继续搜索分页。选项范围不随当前选择收缩，避免改变筛选语义。预加载结果缓存在运行目录 `filter-options/`，键包含字段和关联数据版本，删除后可重建。

页面以看板、数据版本、字段、数据集、搜索词和页号缓存筛选页，并复用进行中的相同请求；缓存最多256页。失败请求不缓存。大响应最多同时读取4个分块，仍校验顺序、完整字节数和JSON；不截断、抽样或丢弃图表数据。选项接口耗时现在可以在 `runtime_diagnostics` 的 `query_complete` 阶段查询。
