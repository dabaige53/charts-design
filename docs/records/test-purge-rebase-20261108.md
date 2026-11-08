# 测试清剿变基记录：2026-11-08

对象：把 `563f159`（基线 `770d4cf`）变基到 `ae77261`（PR #6 合并后的 main）。[原清单](test-purge-20261106.md)保留 `770d4cf` 时的判定和行号，本文只记录变基后的差异，行号指本分支。

## 冲突处理

| 文件 | 冲突 | 处理 |
| --- | --- | --- |
| `tests/runtime/test_declarations.py` | 分支在 parametrize 上方加标注，PR #6 把范围改成 `range(1, 17)` | 两者都保留；PR #6 的 `catalogEntries: 57`、`registeredKpiTypes: 16` 自动合并后仍在 |
| `tests/runtime/test_icon_contract.py` | 分支删除 `test_all_original_contracts_are_explicit`，PR #6 把其断言从 49 改成 56 | 保留用例和 56，恢复 `validate` 导入，标 `debt=D3`，是否删除待决定 |

与 main 的 AST 对比：删除 19 个测试定义，与原清单 20 条 DELETE 相比只差上面保留的 1 条；其余函数全部相同；其他差异只有标注和原清单登记的孤儿导入、常量。

## 规则来源

仓库内没有 D 规则的定义，只有原清单的命中记录。本次按其先例套用，含义是反推的：D1 条件跳过，D3 只查常量或声明，D6 依赖内部实现。

## 新增标注

共 29 处：PR #6 新增 28 个测试定义和 `tests/deploy/container_smoke.py` 的验收入口。其中 `bindings.test.mjs`、`test_generation.py` 各 1 条及 `container_smoke.py` 不在最初列出的 5 个文件内，为保持全覆盖一并标注。

| 文件:行号 | 用例名 | 处置 | 命中 D 规则 | type | protects | 理由 |
| --- | --- | --- | --- | --- | --- | --- |
| tests/runtime/test_server.py:27 | test_signer_rejects_tampering_kind_and_expiry | REWRITE | D1 | boundary | 篡改过期或错类型令牌被接受 | 检查错kind错密钥改签名过期和乱串均被拒；12至13行模块importorskip会整文件跳过，按D1待改写 |
| tests/runtime/test_server.py:40 | test_projects_stay_inside_the_workspace | REWRITE | D1 | boundary | 项目参数逃逸工作区或非法名称被接受 | 枚举工作区外路径和非法名称并校验错误码；同一模块级跳过，按D1待改写 |
| tests/runtime/test_server.py:55 | test_configuration_requires_tokens_and_loopback_trials | REWRITE | D1 | boundary | 无令牌或非回环地址免认证启动及签名密钥权限过宽 | 检查缺令牌短令牌非回环免认证及密钥稳定和0600权限；同一模块级跳过，按D1待改写 |
| tests/runtime/test_server.py:69 | test_view_links_cannot_write | REWRITE（待决定） | D1,D3 | boundary | 只读或编辑链接可调用越权工具 | 只比较VIEW_TOOLS和EDIT_TOOLS常量未发请求，规则倾向删除；只标注不删，见待决定项 |
| tests/runtime/test_server.py:124 | test_remote_mcp_preview_link_and_scoped_viewer_api | REWRITE | D1 | integration | 跨项目读写或只读链接写入或撤销后链接仍可用 | 真实HTTP和MCP客户端检查越权401403撤销CSP和签名下载；同一模块级跳过，按D1待改写 |
| tests/runtime/test_server.py:184 | test_share_pages_render_dashboard_and_report_read_only | REWRITE | D1 | integration | 只读页出现编辑入口或令牌留在地址栏或图表不渲染 | 真实Chromium检查无编辑入口令牌清除和图表渲染；模块级跳过且186至187行未构建时跳过 |
| tests/runtime/test_server.py:215 | test_viewer_api_refuses_oversized_bodies_before_reading | REWRITE | D1 | boundary | 超大请求体被读取或分块接口对链接开放 | 声明超大长度检查413和错误码及分块接口403；同一模块级跳过，按D1待改写 |
| tests/runtime/test_layouts.py:39 | test_every_template_is_valid_on_every_breakpoint | KEEP | - | behavior | 模板在某断点越界重叠或漏组件 | 参数化全部模板检查越界重叠漏组件和保存结果 |
| tests/runtime/test_layouts.py:48 | test_templates_produce_distinct_desktop_compositions | KEEP | - | behavior | 不同模板退化成相同构图或比例错误 | 比较模板构图差异并检查各模板关键几何 |
| tests/runtime/test_layouts.py:67 | test_template_is_applied_after_components_created_in_the_same_batch | KEEP | - | behavior | 同批次后创建的组件未进入模板布局 | 先应用模板后建组件检查新组件进入布局 |
| tests/runtime/test_layouts.py:79 | test_saved_template_reflows_and_manual_layout_replaces_it | KEEP | - | behavior | 增删组件不重排或手动布局被模板覆盖 | 增删组件后检查重排及手动布局替换模板 |
| tests/runtime/test_layouts.py:95 | test_new_components_pack_by_role_instead_of_stacking_full_width | KEEP | - | behavior | 新增KPI和图表堆成整行或挤到高图旁 | 检查新KPI成行图表成对且不贴高图 |
| tests/runtime/test_layouts.py:118 | test_invalid_templates_and_orders_are_rejected | KEEP | - | boundary | 未知模板或缺失组件顺序被接受 | 检查未知模板缺失组件和存量非法模板的拒绝 |
| tests/runtime/test_kpi_cards.py:22 | test_every_guide_example_is_a_valid_card | KEEP | - | integration | 对外示例不能生成对应类型指标卡 | 参数化全部示例经apply_operations校验并核对类型 |
| tests/runtime/test_kpi_cards.py:37 | test_malformed_shapes_are_rejected | KEEP | - | boundary | 分位倒序或负比例等非法配置被接受 | 七类非法配置均被KPI contract拒绝 |
| tests/runtime/test_kpi_cards.py:43 | test_discovery_explains_each_shape_instead_of_one_generic_example | REWRITE（待决定） | D3 | behavior | 按类型选择却拿到通用示例或错误绑定说明 | 主要比较发现结果的固定数量标志和字段集合未应用示例；按类型选择的断言有价值，判D3待改写 |
| tests/runtime/test_kpi_cards.py:55 | test_snapshot_only_shapes_refuse_bindings | KEEP | - | boundary | 仅快照类型被错误绑定数据 | 绑定被拒并校验BINDING_TRANSFORM_REQUIRED |
| tests/runtime/test_kpi_cards.py:62 | test_bound_shapes_recompute_numeric_geometry_under_filters | KEEP | - | integration | 筛选后几何字段或文本未按真实数据重算 | 经dashboard_view检查筛选前后具体数值；81行读store仅用于准备筛选 |
| tests/runtime/test_recommend.py:14 | test_rules_cover_only_registered_codes_and_every_intent | REWRITE | D6 | behavior | 推荐未注册图表或某意图无结果 | 15至17行比较私有_registry；18行各意图有结果仍有价值，同test_legacy_registry先例判D6 |
| tests/runtime/test_recommend.py:22 | test_shape_and_existing_page_steer_the_ranking | KEEP | - | behavior | 排序忽略数据形状或页面已用图表 | 检查分类数和页面已用图表改变排序及提示 |
| tests/runtime/test_recommend.py:34 | test_time_requirements_and_kpi_suggestions | KEEP | - | behavior | 无时间字段仍优先趋势图或KPI建议错误 | 比较有无时间字段评分并检查KPI建议和绑定标记 |
| tests/runtime/test_recommend.py:45 | test_invalid_requests_fail | KEEP | - | boundary | 非法意图或参数类型被接受 | 参数化缺意图未知意图非法分类和类型 |
| tests/runtime/adaptive.test.mjs:10 | legacy containLabel grids make room for an end-placed x-axis name | KEEP | - | behavior | 末端坐标轴名被裁切或未声明containLabel的网格被改动 | 检查末端轴名留白及不适用时不改动 |
| tests/runtime/adaptive.test.mjs:20 | crowded category labels truncate, and rotate only when slots are tiny | KEEP | - | behavior | 拥挤标签重叠或宽裕时被多余截断旋转 | 检查截断旋转宽裕和dataZoom四种情况 |
| tests/runtime/adaptive.test.mjs:33 | legends scroll when they cannot fit, and narrow value labels avoid overlap | KEEP | - | behavior | 图例放不下时溢出或窄图数值标签重叠 | 检查图例滚动标签避让及宽裕时不改动 |
| tests/runtime/adaptive.test.mjs:43 | width buckets and degenerate input | KEEP | - | boundary | 断点错位或空配置零宽度时报错 | 检查断点边界空配置和零宽度 |
| tests/runtime/bindings.test.mjs:68 | bullet, comparison and mini-bar KPIs keep geometry numeric while headlines stay formatted | KEEP | - | behavior | 筛选后几何字段变成文本或数值未重算 | 筛选后检查具体数值字段类型和月度序列 |
| tests/runtime/test_generation.py:71 | test_operations_case_contrasts_the_executive_case_and_recomputes | KEEP | - | integration | 运营案例与高管案例雷同或筛选后指标未重算 | 比较两案例组件类型并检查Doctor和筛选后数值 |
| tests/deploy/container_smoke.py:107 | run_checks | KEEP | - | integration | 部署后鉴权失效或编辑批次失败或只读链接可写 | CI验收入口；真实HTTP检查鉴权编辑批次预览只读写入403和下载；/health轮询有截止时间，不算固定等待 |

另有 2 处调整：PR #6 在 `tests/test_local_mcp_update.py` 加了模块级 `importorskip`，所以 `test_only_chart_entry_changes` 的 debt 改为 `D1,D7`，`test_unknown_entry_is_rejected` 由 KEEP 改为 `debt=D1`。

## 计数

| 项 | 原清单 | 变基后 |
| --- | ---: | ---: |
| DELETE | 20 | 19 |
| KEEP | 254 | 273 |
| REWRITE | 76 | 87 |
| `@wu-test` 标注 | 330 | 360 |

## 待决定项

规则倾向删除，本次只标注，未删除。

1. `tests/runtime/test_icon_contract.py:22` `test_all_original_contracts_are_explicit`：原判 DELETE D3。这是全组件夹具数量唯一的断言，浏览器用例遍历夹具但不校验总数，删除后夹具少组件不会报错。建议保留，或把数量断言并入浏览器用例后再删。
2. `tests/runtime/test_server.py:69` `test_view_links_cannot_write`：D3，只比较常量。只读链接写入已有 HTTP 用例覆盖，但编辑链接不能调用 `dataset_import`、`query_execute`、`dataset_attach`、`dashboard_create` 没有 HTTP 用例。建议改写成 HTTP 断言后再删旧用例。
3. `tests/runtime/test_kpi_cards.py:43` `test_discovery_explains_each_shape_instead_of_one_generic_example`：边界情况，与已删的 `test_public_metadata_and_table_heading_contract` 相似，但按类型选择的断言有价值，暂判 REWRITE。建议保留。

## 验证

环境：macOS，Python 3.11.13，Node 26.11.1，ruff 0.16.9，依赖取自主检出的 `.mcp-test-deps`。

| 命令 | 结果 |
| --- | --- |
| `npm run check` | 通过 |
| `ruff check` | 通过 |
| `npm run test:unit` | pytest 340 通过，Node 90 通过，独立生成器 85 通过，0 跳过 |
| 覆盖率门槛（`--cov-fail-under=84`） | 85.45%，通过 |
| `npm run test:browser`，第 1 轮 | 1 failed, 41 passed, 340 deselected in 107.84s (0:01:47) |
| `npm run test:browser`，第 2 轮 | 未完成 |
| main 干净副本对照 `npm run test:browser` | 未完成 |

第 1 轮失败的是 `test_mcp_projects_browser.py::test_two_project_previews_share_one_connection`，错误发生在 `stdio_client` 退出的清理阶段（`BrokenResourceError`），单独重跑 3 次均通过。该文件在本分支只多一行注释。

未验证：CI 使用的 Linux、Python 3.10 与 3.13、Node 22，以及 `npm run test:container`。
