# 看板创作 MCP 工具审查

后续调整 `server-v1.2.35` 统一了本地、服务器直连与 Magpie 的工具清单。在下表 19 项基础上增加 `dataset_repartition`，共 20 项。Agent 在同一连接中指定需要分片的 COS 数据集和业务字段。普通读者继续通过界面的筛选、查看与导出操作使用看板。下文的 `release` 连接是 `1.2.33` 时的设计记录。

2026-11-25，以本地 stdio MCP 的 `tools/list` 为基线。原 `model` 连接返回 44 项。以下每一行对应原清单的一项，另列远程签名分享的两个入口。

## 用真实项目数据走一遍

任务是做一张 Charts Design 仓库最近七个完整上海自然日的主线提交看板，需要合计、每日明细、可核对的口径和 HTML 文件。数据源固定为 `git log --first-parent --format=%ct 61cb6740c5e8bf69cedd0fb12dabe6203059388f`，按提交者时间归日，包含合并提交。11 月 18–24 日依次为 0、0、0、1、0、4、13 次，共 18 次。

| 实际调用 | 业务判断 |
| --- | --- |
| `dashboard_submit` | 选择名称、主线口径、补零规则、指标与明细。传 `createTitle` 和初始声明，程序创建看板，写入七行数据、指标和两个组件，检查并保存。旧流程先调用 `dashboard_create`，再传递版本号。 |
| `dashboard_view` | 将合计与逐日值对回 Git。传 `includeEvidence: true`，同一响应返回来源、指标定义和单位。旧流程在此还调用 `query_inspect`、`semantic_inspect`。 |
| `dashboard_preview` | 交付已保存的互动预览，核对返回的版本。 |
| `dashboard_export` | 交付指定的 HTML 文件，检查文件包含每日明细标题。 |

各次运行使用真实 MCP 会话和独立本地项目。工具调用从 7 次变为 4 次，未计协议初始化、工具发现或大结果资源读取。此次未执行浏览器视觉验收。其余入口按各自适用的任务审查，未在此案例中调用。

## 创作连接的 19 项

| 工具 | Agent 需要判断什么 |
| --- | --- |
| `dashboard_list` | 目标名称不明确时，判断应该续改哪张看板。 |
| `dashboard_get` | 根据现有声明决定改哪些组件，保留哪些口径与绑定。 |
| `dashboard_create` | 导入已审阅的完整文档，或按需建立空看板供后续导入数据。初始声明齐备时直接提交。 |
| `dashboard_submit` | 声明业务修改；程序按版本执行编辑、检查、保存。 |
| `dashboard_view` | 选择组件、筛选切片和核对依据，对计算结果作业务判断。 |
| `dashboard_preview` | 决定向用户展示哪张已保存的看板。 |
| `dashboard_filter_options` | 查询特定筛选的可选值，确定业务分群。已知取值时可直接查看切片。 |
| `component_data` | 选择要深入核对的组件和明细范围，处理汇总无法回答的问题。 |
| `dashboard_annotations` | 判断读者反馈指向哪个组件、需要改变什么。 |
| `dashboard_annotations_update` | 决定如何处理批注；独立保存，防止编辑看板时覆盖反馈。 |
| `dataset_import` | 选择输入数据、粒度与目标数据集。程序返回写入版本和行数。 |
| `dataset_attach` | 选择已配置的数据源和表，程序完成接入并返回引用。 |
| `query_execute` | 选择查询范围、关联与聚合规则，使数据符合业务口径。 |
| `chart_recommend` | 问题有多种表达方式时，提供分析意图，由程序筛选候选。 |
| `chart_declarations` | 对所选图型按需读取绑定要求，用来判断当前字段能否表达所需比较。 |
| `statistical_render` | 选择统计分析方法、变量和分组；程序生成图形。 |
| `dashboard_export` | 确定需要交付的看板文件格式。 |
| `dataset_export` | 决定交付哪份底层数据，供读者复算。 |
| `dashboard_export_site` | 交付可独立部署的网站包，包括页面及所需资源。 |

## 固定步骤和参考资料的 10 项

| 原工具 | 现在从哪里取得结果 |
| --- | --- |
| `chart_catalog` | 静态图型目录从 `charts://catalog` 读取。 |
| `layout_templates` | 模板从 `charts://layouts` 读取，选定后在提交中应用。 |
| `generation_examples` | 从 `charts://examples` 和各案例资源读取。 |
| `dashboard_data_inspect` | 数据写入回执提供版本、行数；已有看板从声明取数据引用。 |
| `dashboard_doctor` | 提交自动检查组件，问题随提交返回。独立诊断留给排错。 |
| `dashboard_validate` | 提交负责校验。 |
| `query_inspect` | 查看组件时可一起取得数据来源、有效筛选及数据引用。 |
| `semantic_inspect` | 同一次查看可取得指标口径和单位。 |
| `runtime_diagnostics` | 连接故障的运行诊断，交由维护方按需执行。 |
| `runtime_info` | 进程和运行环境信息，交由维护方检查。 |

## 版本与发布

`release` 连接在创作工具之外提供以下入口。前 15 项计入原来的本地 44 项。最后两项需要服务端支持签名分享。任务状态和重试属于运维动作，目前仍由发布连接显式调用。

| 工具 | 发布或运维时的决定 |
| --- | --- |
| `dashboard_history` | 查找可能需要回看的保存点。 |
| `dashboard_history_diff` | 选择两个版本，判断内容变化是否符合预期。 |
| `dashboard_restore` | 决定将哪个保存点恢复成草稿。 |
| `dashboard_version_get` | 阅读指定历史版本的内容。 |
| `dashboard_version_status` | 了解草稿、已保存和发布状态，决定下一步。 |
| `dashboard_version_label` | 给业务里程碑命名。 |
| `dashboard_version_publish` | 决定发布哪个已保存版本。 |
| `dashboard_version_delete_preview` | 删除前判断影响范围是否符合授权。 |
| `dashboard_version_delete` | 确认删除指定版本。 |
| `dashboard_version_delete_status` | 在删除任务未完成时查看进度，无新增业务判断。 |
| `dashboard_version_delete_retry` | 失败后判断是否适合再次执行删除任务。 |
| `dashboard_share_status` | 查当前分享对象和状态，决定保留、替换或撤下。 |
| `dashboard_share_publish` | 决定创建对外分享。 |
| `dashboard_share_replace` | 决定让现有分享指向新内容。 |
| `dashboard_share_delete` | 决定撤下指定分享。 |
| `dashboard_share` | 创建远程签名访问入口，选择访问范围。 |
| `dashboard_share_revoke` | 决定撤销这张看板已发出的全部签名链接。 |
