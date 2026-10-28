# 项目资产与渐进加载

## 存储

启动参数为 `--project-root <project> --runtime-root <runtime> mcp`。项目内 `charts-project.json` 管理历史和加载参数；`dashboards/dashboards.sqlite3` 是事务索引与权威状态，`dashboards/<id>/draft.json`、`checkpoints/*.json`、`annotations.json` 和 `annotation-history.json` 是自动生成的可读镜像，不能另行手工维护。`data/data.sqlite3` 保存不可变数据版本。运行目录仅用于传输缓存及诊断；删除新运行缓存不删除项目资产。既有集中目录不自动清理。

项目默认配置：普通检查点保留100个，筛选合并150毫秒，最多4个组件查询并发，表格50行。命名和发布检查点保护。数据不自动清理，避免删除仍被历史或批注引用的数据。设计JSON和数据内容不应作为含敏感数据的公共仓库产物提交。

## 编辑与展示

`dashboard_edit_begin` 开始或恢复批次；`dashboard_patch` 只保存草稿并发编号。`dashboard_edit_finish` 完整检查后生成一个检查点，成功返回 `nextAction: dashboard_preview`。调用方只在完成后调用一次预览。所有其他工具不声明 UI 资源，不自动打开新页面。已有页面通过版本检测原位更新；宿主是否复用打开的侧栏由宿主控制。

`dashboard_history` 分页读取检查点；`dashboard_history_diff` 比较；`dashboard_checkpoint` 创建、命名或标记发布当前检查点；`dashboard_restore` 默认恢复设计及对应数据引用，可用 `useCurrentData` 明确保留当前数据。批注独立保存，不随设计恢复。历史文档中的批注变更保存在独立事件记录。

## 加载

项目模式预览返回结构和数据版本，不返回全组件计算结果。页面按可见组件调用 `dashboard_view`，使用 `componentIds`、`responseMode: patch`、`expectedRevision`、`dataVersion`、`filterSequence`。请求按最新筛选代次更新；旧响应不覆盖当前筛选。表格分页和筛选选项独立查询。临时点击下钻不持久化为设计版本。

## 诊断

`dashboard_doctor` 的 quick/full 模式检查定义、数据引用与组件计算。结果带请求编号，设计、数据和 UI 版本。完整批次检查失败不生成检查点。`runtime_diagnostics` 支持看板、请求编号、阶段及错误码过滤。页面提供运行诊断入口。检查通过不等于宿主实际页面验收通过。

## 迁移

`--project-root <destination> --runtime-root <cache> migrate-project --source-root <legacy> --board <id>` 先列清单；加 `--apply` 才迁移。只复制选中看板及其历史引用的数据版本，流式核对数据引用，保留历史编号和批注事件；不删除源数据。目标已有同名看板时拒绝覆盖。
