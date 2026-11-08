# 测试清剿记录：2026-11-06

后续：2026-11-08 变基后部分判定和计数有变化，见[变基记录](test-purge-rebase-20261108.md)。本文保留当时事实。

## 范围与计数

- 基准提交：`770d4cf90d14e2fce49a102e78004bfc8b763266`；下表路径和行号均指该版本。
- 用例按测试定义计数；一个参数化定义计一个，不按展开后的执行次数计数。
- 自动测试定义：347 → 327；删除 20，待改写 73，合格保留 254。
- 手动验收入口：3 → 3；均标记 REWRITE。
- 合计：350 → 330；DELETE 20，REWRITE 76，KEEP 254。实际完成逻辑改写 0，本次仅登记待改写项。
- 自动测试文件：84 → 84；含手动验收脚本的文件：87 → 87。没有删空的文件，D13 为 0。
- `@wu-test` 覆盖：330 / 330（100%）。
- REWRITE 用例只补齐标记并记录 debt；本次未改写其测试实现。
- 扫描全部 90 个受版本控制的测试文件与附属脚本，以及 7 个旧测试输入/输出；对每个测试定义逐条判定。排除 node_modules、.mcp-test-deps、.venv、.runtime-installs、.git 和运行缓存中的第三方或副本。
- 3 个 explorer 只读扫描，主会话执行清单并复核纯源码、常量、过度 mock 和条件跳过项。
- 所有保留实现保持不变；未改业务代码，未新增测试。

## DELETE 规则排行

| 规则 | 次数 |
| --- | ---: |
| D6 | 9 |
| D3 | 8 |
| D7 | 2 |
| D4 | 2 |
| D5 | 2 |
| D8 | 1 |

一条 DELETE 可命中多条规则，规则总次数可以大于删除用例数。D12/D13 附属资产另表统计。

## 处置清单

| 文件:行号 | 用例名 | 处置 | 命中 D 规则 | type | protects | 理由 |
| --- | --- | --- | --- | --- | --- | --- |
| tests/runtime/annotation-context.test.mjs:6 | only advertised composer extension enables replacement | KEEP | - | boundary | 未声明能力的宿主收到替换请求 | 对比有无 experimental 能力 |
| tests/runtime/annotation-context.test.mjs:10 | attachments accumulate, preserve location and filters, and follow host removal | KEEP | - | integration | 位置筛选丢失或宿主移除后继续累积旧附件 | 检查两次附件、位置、筛选和移除后数量 |
| tests/runtime/annotation-context.test.mjs:20 | rejection does not mark failed attachment as accepted | KEEP | - | behavior | 失败附件在重试时重复出现 | 首次拒绝后重试检查附件数为1 |
| tests/runtime/annotation-context.test.mjs:27 | composer references identify the owning project when dashboard IDs repeat | KEEP | - | behavior | 同 ID 看板引用错误项目 | 检查 projectRoot 和 dashboardId |
| tests/runtime/annotations.test.mjs:5 | annotation follows a moved and resized component | KEEP | - | behavior | 组件移动缩放后批注位置错误 | 相对坐标转换后检查绝对矩形 |
| tests/runtime/annotations.test.mjs:9 | selection stays within target bounds | KEEP | - | boundary | 选择区域超出目标 | 越界矩形被限制为完整目标范围 |
| tests/runtime/benchmark_incremental.py:25 | run | REWRITE | D6,D9 | integration | 连续翻页后图表失效或资源持续增长 | 59至61行读取内部实例83至85行实例数堆监听器断言依赖实现GC环境无当前预算 |
| tests/runtime/benchmark_local.py:101 | run_benchmark | REWRITE | D6,D10,D11 | integration | 大数据查询分页或完整导出结果错误 | 32行expected_totals及152行复制聚合125至126行自算期望158至162行直接查SQL历史 |
| tests/runtime/bindings.test.mjs:9 | original bars and table use the same explicit filter without mutating the source | KEEP | - | behavior | 筛选结果错误或修改原始配置 | 检查East聚合120和原值999；名称提到table但正文只测bar |
| tests/runtime/bindings.test.mjs:13 | original KPI ratio recomputes numerator/denominator | KEEP | - | behavior | 筛选后KPI沿用旧比例或旧同比 | 检查82.73%及缺失同比 |
| tests/runtime/bindings.test.mjs:18 | quarterly dual-axis ratio is not an average of monthly percentages | KEEP | - | behavior | 季度比例使用月比例平均 | 检查季度分类总额和81.67 |
| tests/runtime/bindings.test.mjs:22 | metric decimals set the shown precision after scaling | KEEP | - | behavior | 缩放后的指标忽略小数位 | 检查季度比例取整为82 |
| tests/runtime/bindings.test.mjs:26 | filtered KPI comparisons retain signs, units and neutral zero | KEEP | - | behavior | 筛选后同比环比符号或缺失值错误 | 检查正负零和缺失输出 |
| tests/runtime/bindings.test.mjs:40 | rounded zero never receives a positive or negative sign | KEEP | - | behavior | 四舍五入为零后仍显示正负号 | 检查正负极小值及单位 |
| tests/runtime/bindings.test.mjs:45 | bubble aggregation follows filters and keeps the clicked agent identity | KEEP | - | integration | 气泡筛选结果或联动身份错误 | 检查聚合坐标透明度身份和空结果 |
| tests/runtime/echarts-options.test.mjs:12 | native overrides preserve preset data/functions and accept extra fields | KEEP | - | behavior | 覆盖配置丢失原数据或函数 | 检查按id合并空值和原对象不变 |
| tests/runtime/echarts-options.test.mjs:34 | column preset renders native colors, labels and axis options | KEEP | - | integration | 原生颜色标签或坐标配置不生效 | 检查SVG及渲染后颜色轴角度 |
| tests/runtime/echarts-options.test.mjs:47 | bubble visualMap category colors stay stable after filtering | KEEP | - | integration | 筛选后类别颜色变化 | 两组数据均检查Agent B颜色 |
| tests/runtime/echarts-options.test.mjs:60 | full runtime registers native custom rendering and brush modules | KEEP | - | integration | 自定义图形或brush在实际渲染中不可用 | 创建custom图形并检查渲染颜色与brush组件 |
| tests/runtime/echarts-options.test.mjs:68 | bound recomputation retains option overrides without replacing computed values | KEEP | - | integration | 覆盖配置替换筛选计算数据 | 检查计算值12标签覆盖及源数据999 |
| tests/runtime/encoding.test.mjs:6 | scatter ratio, fixed size, null and filtering | KEEP | - | behavior | 比例缺失值或空筛选结果错误 | 检查0.19 null尺寸与空系列 |
| tests/runtime/encoding.test.mjs:7 | dynamic horizontal stack and missing pairs | KEEP | - | behavior | 分类排序堆叠或缺失组合错误 | 检查排序系列颜色和null数据点 |
| tests/runtime/encoding.test.mjs:8 | retail region × product supports changing group dimension and filtered series | KEEP | - | behavior | 更换维度或筛选后系列错误 | 检查缺失分类筛选后系列及数值 |
| tests/runtime/encoding.test.mjs:9 | attribute conflicts return null and size encoding is opt-in | REWRITE | D7 | behavior | 冲突属性被误展示或尺寸编码失效 | null有具体断言但sizeBy只检查返回function |
| tests/runtime/encoding.test.mjs:11 | top-series remainder keeps total bar lengths and descending category order | KEEP | - | behavior | 其他系列合并后总量或顺序错误 | 检查系列名称总量提示和筛选结果 |
| tests/runtime/encoding.test.mjs:27 | each category selects its own top five and merges the remainder | KEEP | - | behavior | 不同类别共用错误的前五系列 | 检查各类别名称余量及总数 |
| tests/runtime/engine.test.mjs:6 | weighted ratio is recomputed, not mean of percentages | KEEP | - | behavior | 比例按百分比平均或零分母产生错误值 | 检查91/110和零分母null |
| tests/runtime/engine.test.mjs:10 | filters feed KPIs and charts from the same reviewed rows | KEEP | - | integration | KPI与图表使用不同筛选范围 | 检查行数及双方总额278 |
| tests/runtime/engine.test.mjs:16 | native chart type switching preserves source snapshot | KEEP | - | behavior | 切换图表类型更改源数据或类型错误 | 遍历图表类型并检查snapshot |
| tests/runtime/engine.test.mjs:25 | shape compatibility blocks missing roles | KEEP | - | boundary | 字段角色不足时启用不兼容图表 | 检查scatter heatmap waterfall的拒绝与允许 |
| tests/runtime/engine.test.mjs:35 | null measurements are missing, never coerced to zero | DELETE | D4 | - | - | 仅检查null求和；static-performance.test.mjs:16覆盖同输入同结果 |
| tests/runtime/engine.test.mjs:38 | CSV quotes values and neutralizes formula injection | KEEP | - | boundary | 公式注入及引号破坏CSV | 使用CSV解析器检查公式转义和负数 |
| tests/runtime/engine.test.mjs:45 | declared search recomputes only its explicit consumers | KEEP | - | behavior | 搜索影响未绑定组件 | 检查目标组件行数总额和details不变 |
| tests/runtime/entity-ratio.test.mjs:4 | entity ratio nets rows by channel before counting and preserves missing | KEEP | - | behavior | 同实体正负记录未抵消或空数据误计 | 检查1/3空集合及缺失值 |
| tests/runtime/filter-controls.test.mjs:13 | office dropdown replaces one office at a time and supports all offices | KEEP | - | behavior | 单选筛选累积旧值 | 检查依次选择及清空的回调值 |
| tests/runtime/filter-controls.test.mjs:26 | clear all removes every condition and preserves its definition | KEEP | - | behavior | 清除条件破坏筛选定义或原数据 | 检查所有值清空selectionMode及原值 |
| tests/runtime/filter-controls.test.mjs:34 | exported current-view HTML does not enable incomplete local filtering | DELETE | D3,D5 | - | - | 只传disabled=true后检查disabled属性，未执行或验证离线导出的禁用决策 |
| tests/runtime/filter-controls.test.mjs:39 | a filter can cancel all draft checks, pick one value, or select all | REWRITE | D6 | behavior | 取消全选和重新选择产生错误条件 | 通过固定children数组下标操作控件 |
| tests/runtime/filter-controls.test.mjs:54 | cancel all also clears selected values on unloaded pages | REWRITE | D6 | behavior | 未加载页保留已取消选项 | 固定children下标驱动分页选择但最终回调有行为断言 |
| tests/runtime/filter-controls.test.mjs:64 | excluding one value from all retains the values on unseen pages | REWRITE | D6 | behavior | 排除一项时丢失未加载页选项 | 固定children下标操作并检查B C结果 |
| tests/runtime/filter-controls.test.mjs:72 | required month has no all entry and clear preserves the selected month | KEEP | - | boundary | 必选月份被清空 | 检查菜单无全部项及清除后的月份 |
| tests/runtime/host-app.test.mjs:5 | real SDK initialization preserves composer capabilities | KEEP | - | integration | SDK解析后丢失composer能力 | 使用真实schema解析再检查扩展能力 |
| tests/runtime/lifecycle.test.mjs:5 | visible preview renews; hidden or closed preview stops; restored page resumes | KEEP | - | behavior | 隐藏页继续续期或恢复后不续期 | 模拟可见性页面事件检查计时器及回调 |
| tests/runtime/lifecycle.test.mjs:22 | host teardown stops refresh and keepalive before pagehide | KEEP | - | behavior | 宿主销毁后继续刷新和保活 | dispose后检查计时器清空及事件无新调用 |
| tests/runtime/local_browser_acceptance.py:29 | accept | REWRITE | D6,D9,D11 | integration | 筛选搜索分页CSV丢行或原版展示不一致 | 126行复制搜索计数161行固定500ms等待167至170行内部图表表格状态 |
| tests/runtime/mcp-reload.test.mjs:7 | update drains in-flight request and replays initialization before queued request | REWRITE | D5,D6 | integration | 更新时丢失在途请求或未初始化即处理新请求 | VM模拟fs readline子进程和流且依赖内部发送顺序 |
| tests/runtime/progressive.test.mjs:5 | visible requests only; stale filter response cannot apply | REWRITE | D9 | behavior | 旧筛选响应覆盖新结果或请求不可见组件 | tick固定等待10ms |
| tests/runtime/project-context.test.mjs:6 | two previews retain their projects for background, view, edit and annotation calls | KEEP | - | boundary | 同ID看板跨项目请求或接受其他项目结果 | 检查各调用projectRoot及跨项目拒绝 |
| tests/runtime/project-context.test.mjs:26 | initial chunked result binds context before requesting chunks | KEEP | - | integration | 首个分块请求发往错误项目 | 检查分块projectRoot与解码结果 |
| tests/runtime/project-context.test.mjs:41 | legacy hosts and startup project defaults retain their request shape | KEEP | - | behavior | 旧宿主请求形状变化或启动项目丢失 | 检查无项目参数与默认项目参数 |
| tests/runtime/ranking-zoom.test.mjs:13 | `${code} keeps a bounded window without discarding categories` | KEEP | - | integration | 图表窗口丢分类或无法回到首项 | 参数化c01 t01检查可见数量及缩放后的首项 |
| tests/runtime/ranking-zoom.test.mjs:30 | large rankings render a readable window and can reach the last category | KEEP | - | integration | 大排行末项不可达或导出被截断 | 检查12项窗口末项完整表格及恢复 |
| tests/runtime/ranking-zoom.test.mjs:55 | small or filtered rankings show all remaining rows without a redundant slider | KEEP | - | behavior | 小数据集显示多余滑块或丢行 | 检查0 1 12行时无dataZoom且行数完整 |
| tests/runtime/report.test.mjs:5 | Markdown prose surrounds inline chart fences, while ordinary code stays code | KEEP | - | behavior | 图表插入破坏正文顺序或普通代码被执行 | 检查图表数量HTML与先后位置 |
| tests/runtime/report.test.mjs:9 | Invalid and missing chart references are inline errors, not execution | KEEP | - | boundary | 无效组件引用或危险HTML被执行 | 检查无效引用报错及危险标签链接清理 |
| tests/runtime/report.test.mjs:13 | Legacy migration preserves order and canonical Markdown is returned byte-for-byte | KEEP | - | behavior | 迁移打乱顺序或修改已有原文 | 检查旧块顺序及CRLF原文 |
| tests/runtime/report.test.mjs:16 | Paper captions and source notes are plain data with strict bounds | KEEP | - | boundary | 非法类型超长或未知字段进入图注 | 检查合法值及多个非法输入 |
| tests/runtime/report.test.mjs:22 | Footnotes are numbered by first citation and collected after all prose | KEEP | - | behavior | 注释编号或汇总位置错误 | 检查引用顺序编号和正文后汇总 |
| tests/runtime/report.test.mjs:35 | Repeated note references retain one number and return to every occurrence | KEEP | - | behavior | 重复引用产生多个编号或返回链接失效 | 检查三次引用返回链接及ID唯一 |
| tests/runtime/report.test.mjs:47 | Missing note references remain literal with a deduplicated nonblocking warning | KEEP | - | behavior | 缺失注释阻断正文或重复告警 | 检查原文保留单条警告及有效引用 |
| tests/runtime/report.test.mjs:56 | Code blocks, inline code, escaped references and note labels are never executable | KEEP | - | boundary | 代码和转义文本被解析为注释 | 检查无注释生成且代码内容保留 |
| tests/runtime/report.test.mjs:63 | Note bodies keep safe Markdown links and escape HTML and unsafe URL schemes | KEEP | - | boundary | 注释中的HTML或危险链接执行 | 检查安全链接保留及script危险协议转义 |
| tests/runtime/report.test.mjs:73 | Chart-looking code inside notes is inert while top-level charts retain validation | KEEP | - | boundary | 注释内图表代码被执行 | 检查仅顶层图表生成和嵌套引用校验 |
| tests/runtime/report.test.mjs:82 | Footnote render state never leaks to a later report or changes canonical source | KEEP | - | behavior | 不同报告共享注释编号或改变原文 | 连续解析两份报告检查编号和原文 |
| tests/runtime/request-queue.test.mjs:5 | one budget bounds multiple callers and failures release slots | REWRITE | D9 | behavior | 并发超限或失败后队列阻塞 | 用2ms定时器制造并发 |
| tests/runtime/request-queue.test.mjs:12 | column records preserve Unicode, zero, null and negative values | KEEP | - | behavior | 展开记录丢失Unicode零或null | 检查完整展开结果和原对象引用 |
| tests/runtime/static-client.test.mjs:4 | required partition cannot query all months or multiple months | KEEP | - | boundary | 必选分区查询全部或多个分区 | 检查缺失空值多值均报错 |
| tests/runtime/static-client.test.mjs:7 | same-month queries reuse worker; switching month terminates old data owner | REWRITE | D6 | integration | 切换月份后旧数据继续响应或资源不释放 | 主要依赖FakeWorker实例数消息下标及terminate状态 |
| tests/runtime/static-filter-options.test.mjs:3 | static filter supports search, later pages and clearing search with no server | KEEP | - | behavior | 搜索分页遗漏选项或清空搜索后结果错误 | 检查首页末页匹配及清空 |
| tests/runtime/static-filter-options.test.mjs:8 | single office options and carrier text match without changing their exact values | KEEP | - | behavior | 模糊搜索改变原始选项值 | 检查中文大小写及空选项 |
| tests/runtime/static-performance.test.mjs:5 | refresh does not serialize rows; detects replacements and filter changes | DELETE | D6 | - | - | 仅比较内部signature与toJSON禁用，没有观察数据替换后的组件结果 |
| tests/runtime/static-performance.test.mjs:11 | same filter scopes share rows, changing filters or snapshots invalidates results | REWRITE | D6 | behavior | 筛选或数据变化后使用过期结果 | 聚合结果有效但同数组引用断言绑定缓存实现 |
| tests/runtime/static-performance.test.mjs:16 | single-pass aggregates preserve nulls, negatives, ratios and large min/max | KEEP | - | behavior | 空值负数比例及大数组最大值错误 | 检查sum avg min max ratio和20万行不测耗时 |
| tests/runtime/static-query.test.mjs:4 | month filtering loads only matching static partition and reuses it | KEEP | - | integration | 跨月份取错数据或重复加载相同分区 | 检查结果及加载的分区文件 |
| tests/runtime/static-query.test.mjs:11 | table grouping, sort, paging, search and full CSV export use same scope | KEEP | - | integration | 分页排序搜索与导出使用不同数据范围 | 检查分组第二页搜索导出行数 |
| tests/runtime/statistical.test.mjs:8 | Statistical image sources allow only exact embedded SVG/PNG Base64 URLs | KEEP | - | boundary | 远程危险或错误格式图片URL被接受 | 枚举合法及非法协议类型Base64 |
| tests/runtime/statistical.test.mjs:21 | Derived artifacts refresh on responses and clear instead of leaking across documents | KEEP | - | behavior | 切换文档后显示旧统计图 | 检查更新相同响应复用及切换后清空 |
| tests/runtime/statistical.test.mjs:33 | Artifact records are isolated own properties and accept only string display fields | KEEP | - | boundary | 原型污染或非法字段进入展示 | 检查null原型__proto__和非字符串字段 |
| tests/runtime/statistical.test.mjs:54 | Statistical mount creates an inert image with title alt and literal caption | KEEP | - | boundary | 图注HTML执行或图片失败无提示 | 检查字面文本alt错误提示和图片移除 |
| tests/runtime/statistical.test.mjs:68 | Missing, failed and remote artifacts show clear errors without assigning image URLs | KEEP | - | boundary | 缺失或远程图片被加载且无错误提示 | 检查三类错误均无img并显示alert |
| tests/runtime/table-format.test.mjs:11 | percent points keep one decimal and are never multiplied twice | KEEP | - | behavior | 百分点被重复乘100 | 检查百分点和fraction两种比例 |
| tests/runtime/table-format.test.mjs:19 | missing values, comparisons, money and counts retain their own meaning | KEEP | - | behavior | 缺失值正负号和数字精度显示错误 | 检查缺失正负千分位和字符串 |
| tests/runtime/table-format.test.mjs:30 | table rendering uses column precision while preserving source values | REWRITE | D5 | integration | 列精度未显示或源数据被修改 | 伪造context DOM并直接调用prototype方法 |
| tests/runtime/test_annotations_browser.py:9 | test_new_annotation_targets_outer_component | KEEP | - | integration | 点击组件内部元素时批注绑定错误组件 | 保存检查componentId并检查面板轮廓 |
| tests/runtime/test_annotations_browser.py:53 | test_report_annotations_persist_and_report_missing_text | KEEP | - | integration | 刷新后批注丢失或原文删除后批注消失 | 检查图表段落批注保存重载及失效提示 |
| tests/runtime/test_annotations_browser.py:124 | test_composer_submission_keeps_selection_mode | REWRITE | D6 | behavior | 提交第一条后无法选择第二处 | 152与155行直接检查window.annotations.active |
| tests/runtime/test_asset_cache.py:14 | test_asset_reads_are_reused_and_rebuilds_invalidate | REWRITE | D6 | behavior | 构建更新后仍显示旧资源 | 精确比较内部读取次数；同例检查更新删除重建 |
| tests/runtime/test_asset_cache.py:48 | test_runtime_info_reads_revision_without_loading_document | REWRITE | D6 | behavior | 返回过期版本号 | monkeypatch禁止内部store.get但也检查版本变化 |
| tests/runtime/test_binding_browser.py:24 | test_original_filter_binding_and_persisted_table | REWRITE | D1,D9 | integration | 筛选结果不一致或列配置未保存 | 21行条件skip及125行固定等600ms；KPI图表表格保存断言仍保护核心风险 |
| tests/runtime/test_bindings.py:14 | test_binding_roundtrip_preserves_original_config | KEEP | - | behavior | 添加绑定丢失原配置或筛选关联 | 检查config datasetId更新filters |
| tests/runtime/test_bindings.py:23 | test_incomplete_or_unsafe_bindings_fail | KEEP | - | boundary | 缺字段或不安全目标进入配置 | 参数化拒绝缺数据集字段measure非法目标比例 |
| tests/runtime/test_browser.py:16 | test_display_preserves_chart_switch_and_service_updates | REWRITE | D1,D6,D9 | integration | 标题描述和批注修改后无法保存 | 10行模块skip 65至67行GridStack内部对象97行固定等400ms |
| tests/runtime/test_browser.py:110 | test_metadata_and_component_descriptions_survive_render | REWRITE | D1 | integration | 导入描述丢失或组件描述作为HTML执行 | 10行模块skip；正文检查元数据纯文本及更新描述 |
| tests/runtime/test_browser_lifecycle.py:11 | test_visible_preview_keeps_running_and_closed_preview_exits | REWRITE | D9 | integration | 可见页面提前关闭或关闭后服务不退出 | 14行0.6秒真实超时25行固定等1000ms |
| tests/runtime/test_bubble_binding.py:20 | test_bubble_recomputes_scoped_metrics_in_local_view | KEEP | - | integration | 筛选后气泡指标或明细范围错误 | 比较筛选前后聚合明细及缺size拒绝 |
| tests/runtime/test_component_export.py:12 | test_mcp_original_export_uses_shared_ui_and_only_requested_component | REWRITE | D1 | integration | 导出带入其他组件或依赖外部框架 | 解析启动数据仅含请求组件和离线HTML；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_configured_entrypoint.py:14 | test_project_mcp_command_and_reconnect | REWRITE | D1 | integration | 重连丢失保存修改 | 按mcp.json启动创建修改重连读取标题；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_configured_entrypoint.py:42 | test_same_host_session_survives_worker_idle_shutdown | REWRITE | D1,D9 | integration | worker退出后同会话无法读数据 | 两次固定sleep(1)依赖日志计数；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_declarations.py:23 | test_legacy_family_examples_validate | REWRITE | D1 | integration | 对外示例不能生成对应组件 | 三类示例apply_operations检查family；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_declarations.py:32 | test_each_legacy_kpi_selected_example_validates | REWRITE | D1 | integration | 指定KPI返回错误类型或无效示例 | 九种类型逐个选择应用；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_declarations.py:43 | test_legacy_registry_and_catalog_are_distinguished | REWRITE | D1,D6 | behavior | 目录条目被误当可用图表 | 公开r05 tb01 mc01结果有效但比较私有registry固定计数；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_declarations.py:70 | test_index_only_advertises_original_charts | KEEP | - | boundary | 发现接口提供不支持原生图表 | 检查无nativeCharts并拒绝chart_type |
| tests/runtime/test_declarations.py:80 | test_legacy_selection_never_substitutes_a_different_code_example | REWRITE | D1 | integration | 请求t06却得到其他图表示例 | 应用示例检查code和声明；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_declarations.py:97 | test_invalid_selections_fail_explicitly | KEEP | - | boundary | 无效类型或冲突选择被接受 | 参数化错误类型未知值冲突参数 |
| tests/runtime/test_declarations.py:102 | test_discovery_is_detached_json_data | KEEP | - | behavior | 调用方修改结果污染后续发现 | 清空一次operations再读取 |
| tests/runtime/test_declarations.py:110 | test_missing_original_sources_has_no_alternative_chart_system | KEEP | - | boundary | 缺原资源时错误提供其他图表系统 | 空目录检查unavailable和LEGACY_UNAVAILABLE |
| tests/runtime/test_declarations.py:122 | test_contract_exposes_conditional_native_and_legacy_fields | DELETE | D3 | - | - | 只检查CONTRACT字典字段字符串注册项未执行接口或声明行为 |
| tests/runtime/test_declarations.py:130 | test_declarations_do_not_import_transport_modules | DELETE | D6 | - | - | 子进程只检查sys.modules内部导入状态和资源常量 |
| tests/runtime/test_declarations.py:143 | test_advertised_shape_schemas_accept_their_examples | REWRITE | D1 | integration | 对外示例不符合公开schema | JSON Schema校验示例及schema；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_declarations.py:155 | test_advanced_examples_are_legal_own_code_configs | KEEP | - | integration | t06或m01示例不能按指定代码生成 | 应用操作校验code文档绑定能力 |
| tests/runtime/test_declarations.py:165 | test_public_metadata_and_table_heading_contract | DELETE | D3 | - | - | 只比schema属性集合和枚举注册未检查输入行为 |
| tests/runtime/test_declarations.py:173 | test_native_echarts_options_are_discoverable_and_preserved | KEEP | - | boundary | 原生配置丢失或非对象配置被接受 | 检查保存覆盖值及字符串被拒绝 |
| tests/runtime/test_deployment.py:7 | test_site_is_independent_and_keeps_all_used_rows | KEEP | - | integration | 部署缺数据构建文件或泄露查询参数 | 核对数据行数构建文件source内容 |
| tests/runtime/test_drag_browser.py:14 | test_drag_handle_moves_and_saves_without_resizing | KEEP | - | integration | 拖动改变组件尺寸或布局未保存 | 鼠标触摸参数化比较保存前后位置尺寸及撤销 |
| tests/runtime/test_drag_browser.py:90 | test_second_drag_survives_inflight_layout_save | KEEP | - | integration | 首笔保存完成中断正在进行的第二次拖动 | 事件控制首笔保存检查第二次拖动最终布局 |
| tests/runtime/test_encoding.py:6 | test_local_dynamic_aggregate | KEEP | - | integration | 比例属性聚合或空筛选结果错误 | 检查加权比例最小值冲突属性空结果 |
| tests/runtime/test_encoding.py:17 | test_retail_series_and_filter_parity | KEEP | - | integration | 筛选后系列或销售额错误 | South筛选后总额及两个产品系列 |
| tests/runtime/test_encoding.py:28 | test_dynamic_declaration_validation | KEEP | - | boundary | 不存在系列字段被保存 | 合法seriesField保存未知字段抛错 |
| tests/runtime/test_encoding_browser.py:25 | test_dynamic_encoding_browser | REWRITE | D6 | integration | 筛选点击图表后系列和明细不一致 | 39至50行读取私有chartInstances和图表选项 |
| tests/runtime/test_entity_ratio.py:4 | test_entity_ratio_deduplicates_after_filters_and_nets_refunds | KEEP | - | behavior | 筛选后重复计数或退款未抵消 | 检查全量筛选空结果分组比例 |
| tests/runtime/test_executive_product.py:16 | test_search_contract_rejects_wrong_values_and_fields | KEEP | - | boundary | 非字符串多值或数值字段搜索被接受 | 三种非法contains声明失败 |
| tests/runtime/test_executive_product.py:32 | test_visible_filters_union_search_kpi_and_table_export | KEEP | - | integration | 页面筛选KPI导出数据不一致 | 操作筛选搜索读取CSV检查KPI |
| tests/runtime/test_executive_product.py:137 | test_complete_executive_case_has_visible_month_quarter_controls | KEEP | - | integration | 时间切换语义查看导出不可用 | 检查控件版本不变图表切换移动布局 |
| tests/runtime/test_exports.py:9 | test_open_only_a_managed_export | REWRITE | D6 | boundary | 非托管路径或非法动作被打开 | 有非法路径检查但精确断言subprocess参数次数 |
| tests/runtime/test_exports.py:27 | test_symlink_cannot_escape_export_directory | KEEP | - | boundary | 符号链接绕过导出目录限制 | 外部目录链接被拒绝 |
| tests/runtime/test_exports.py:39 | test_report_pdf_contains_only_referenced_tables | KEEP | - | integration | 导出包含未引用私有表格 | 提取PDF文本检查隐藏表标题不存在 |
| tests/runtime/test_fidelity.py:20 | test_original_workspace_import_is_lossless | KEEP | - | integration | 导入丢失组件配置筛选信息 | 写原文件比较每个导入配置 |
| tests/runtime/test_fidelity.py:58 | test_original_toolbar_kpi_table_and_offline_fidelity | REWRITE | D1,D9 | integration | 工具栏表格或离线页面不可用 | 真实交互但移动布局前固定等500ms；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_filter_selection.py:10 | test_single_filter_rejects_multiple_values_and_can_clear | KEEP | - | boundary | 单选保存多值或无法清空 | 拒绝两值接受单值空值 |
| tests/runtime/test_generation.py:7 | test_case_generates_from_blank | KEEP | - | integration | 案例无法从空文档生成看板报告 | 应用两案例检查模式组件绑定正文 |
| tests/runtime/test_generation.py:32 | test_case_discovery_read_only | KEEP | - | boundary | 读取案例创建看板或接受路径穿越 | 检查列表为空拒绝../other |
| tests/runtime/test_generation.py:41 | test_executive_binding_recomputes_data_after_combined_filters | KEEP | - | integration | 多筛选下图表KPI未重算 | Node执行绑定检查月季度KPI |
| tests/runtime/test_generation_mcp.py:17 | test_discover_and_author_independent_academic_report_over_stdio | REWRITE | D1 | integration | 调用方无法发现创建报告或读正确数据 | 真实stdio创建查询并检查非法修改回滚；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_icon_contract.py:21 | test_all_original_contracts_are_explicit | DELETE | D3 | - | - | 只验证测试数据校验组件数49和fixture常量 |
| tests/runtime/test_icon_contract.py:31 | test_every_original_visual_and_icon_header | REWRITE | D1,D9 | integration | 图表控件或移动布局不可用 | 逐组件操作但固定等900ms和500ms；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_idle_lifetime.py:15 | test_busy_request_gets_full_idle_grace_after_completion | KEEP | - | behavior | 长请求结束后立即超时 | 注入时钟检查请求中宽限到期 |
| tests/runtime/test_idle_lifetime.py:28 | test_timeout_cannot_disable_default_cleanup | KEEP | - | boundary | 非正数非有限超时使清理失效 | 0负数NaN无穷大报错 |
| tests/runtime/test_idle_lifetime.py:33 | test_http_keepalive_then_shutdown_preserves_saved_state | REWRITE | D9 | integration | 保活时过早退出或退出丢数据 | 固定sleep(0.1)与0.3秒超时依赖调度 |
| tests/runtime/test_idle_lifetime.py:57 | test_real_mcp_process_exits_without_calls | REWRITE | D1 | integration | 无请求MCP进程持续运行 | 等待进程退出检查状态；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_incremental_browser.py:16 | test_reconcile_modes_resize_refresh_and_repeated_pages | REWRITE | D6 | integration | 刷新或重复翻页后组件失效焦点或数据范围错误 | 34至46及58行直接检查chartInstances gridstack及内部状态 |
| tests/runtime/test_incremental_browser.py:77 | test_latest_search_wins_with_one_active_read | REWRITE | D9 | integration | 旧搜索结果覆盖最新搜索 | 93行sleep(0.5)制造竞态已有事件可显式释放 |
| tests/runtime/test_incremental_queries.py:30 | test_patch_matches_full_and_skips_unselected | REWRITE | D6 | integration | 局部响应与完整视图不一致 | 结果对比有效但禁止内部aggregate filter_options调用 |
| tests/runtime/test_incremental_queries.py:47 | test_empty_patch_and_revision_conflict | REWRITE | D6 | boundary | 空请求返回组件或旧版请求被接受 | 检查空结果409同时禁止内部rows调用 |
| tests/runtime/test_incremental_queries.py:59 | test_refresh_discards_deleted_component_reader_state | KEEP | - | integration | 删除组件后旧筛选引用失效或污染保存 | 删除后检查关联页码未保存筛选 |
| tests/runtime/test_incremental_queries.py:73 | test_component_data_sort_search_and_sequential_pages | REWRITE | D11 | integration | 排序搜索后翻页漏行重复 | 测试重写过滤排序计算expected |
| tests/runtime/test_incremental_queries.py:88 | test_semantic_aggregate_reuses_aliases_and_versions_invalidate | REWRITE | D6 | behavior | 数据版本改变复用旧结果 | 新旧结果有效但禁止内部aggregate调用 |
| tests/runtime/test_incremental_queries.py:108 | test_singleflight_shares_key_without_serializing_unrelated_queries | REWRITE | D9,D6 | behavior | 相同查询重复计算或不同查询互相阻塞 | 固定sleep(.03)协调线程并查私有缓存容量 |
| tests/runtime/test_incremental_queries.py:128 | test_counts_and_options_reuse_cached_sql | DELETE | D6 | - | - | 只查cache.get次数私有缓存键前缀无结果或性能要求 |
| tests/runtime/test_incremental_queries.py:142 | test_sorted_cursor_preserves_nulls_and_duplicate_ties | KEEP | - | behavior | 空值同排序值导致翻页漏行重复 | 连续小页与完整结果比较升降序 |
| tests/runtime/test_incremental_queries.py:154 | test_concurrent_component_reads_and_filters | KEEP | - | integration | 并发筛选分页互相污染 | 多线程交替图表表格读检查一致 |
| tests/runtime/test_incremental_queries.py:164 | test_singleflight_failure_can_retry | KEEP | - | behavior | 首次失败后同查询无法重试 | 首次抛错后重试成功 |
| tests/runtime/test_incremental_queries.py:171 | test_patch_mcp_text_preserves_small_response_for_text_only_hosts | KEEP | - | integration | 纯文本宿主丢失局部视图 | 解析文本比较结果并检查小于48000字符 |
| tests/runtime/test_incremental_queries.py:181 | test_semantic_alias_does_not_collide_with_group_field | REWRITE | D6 | behavior | 指标别名覆盖同名分组字段 | 分组结果有效但也断言cache hit |
| tests/runtime/test_inspector_data.py:8 | test_inspector_reads_all_filtered_pages_and_keeps_revision | KEEP | - | integration | 筛选分页漏行或读取改变版本 | 1005行跨页版本冲突页长上限 |
| tests/runtime/test_inspector_data.py:33 | test_single_page_inspector_online_and_offline | KEEP | - | integration | 语义来源分页在页面不可见 | 两种页面分页SQL定义移动布局 |
| tests/runtime/test_inspector_data.py:89 | test_legacy_explanation_keeps_sql_in_source_and_long_scope_in_rows | KEEP | - | integration | SQL长口径或参数展示错误 | 离线检查SQL定义参数布局 |
| tests/runtime/test_legacy.py:5 | test_legacy_template_uses_explicit_data | REWRITE | D1 | behavior | 标题未转义或占位符残留 | 检查转义占位符消失CSP版本；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_linkage_browser.py:24 | test_chart_click_links_compatible_components_and_blurs_the_rest | KEEP | - | integration | 联动筛错明细误影响未绑定组件或写入看板 | 检查联动标签表格清除及保存版本不变 |
| tests/runtime/test_local_data.py:20 | test_aggregate_null_and_ratio_recomputed | KEEP | - | behavior | 空值空集合比例聚合结果错误 | sum count avg ratio季度分组 |
| tests/runtime/test_local_data.py:33 | test_filter_sort_pagination_and_complete_export | KEEP | - | integration | 筛选排序分页完整导出丢行 | 检查Unicode范围筛选CSV全部行 |
| tests/runtime/test_local_data.py:50 | test_versions_streaming_and_metadata_verification | REWRITE | D6 | behavior | 流式导入版本读取丢数据 | 检查20000行但直接断言内部versions行数 |
| tests/runtime/test_local_data.py:66 | test_injection_and_readonly_import | KEEP | - | boundary | 恶意表名字段名改变查询 | 含SQL语法合法名称导入并拒绝非法字段 |
| tests/runtime/test_local_data.py:85 | test_result_bounds_raise_and_invalid_import_rolls_back | KEEP | - | boundary | 超限非法值被接受并阻断后续导入 | 降低上限拒绝后合法导入成功 |
| tests/runtime/test_local_data.py:99 | test_missing_values_roundtrip_and_lazy_index_reuse | REWRITE | D6 | behavior | 缺字段被转成显式null | 往返版本差异有效但查内部索引数量名称 |
| tests/runtime/test_local_data.py:121 | test_sqlite_declared_boolean_conversion | KEEP | - | behavior | 0和1及null导入语义错误 | 检查转换TRUE搜索 |
| tests/runtime/test_local_data.py:132 | test_search_matches_visible_fields_null_unicode_and_full_export | KEEP | - | boundary | 隐藏字段泄露Unicode失败或导出漏行 | 隐藏null Unicode注入CSV |
| tests/runtime/test_local_data.py:155 | test_table_sort_numeric_display_and_raw_override | KEEP | - | behavior | 格式化数值或原字段排序错误 | 金额百分比日期CSV顺序 |
| tests/runtime/test_local_data.py:172 | test_explicit_null_filter_and_search_exclude_missing_fields | KEEP | - | behavior | 缺字段误判显式null | 对比筛选聚合搜索导出 |
| tests/runtime/test_local_data.py:188 | test_original_field_order_survives_versions_reopen_and_default_csv | KEEP | - | integration | 重开字段顺序变化CSV列错位 | 检查版本重开行默认CSV顺序 |
| tests/runtime/test_local_data.py:211 | test_older_metadata_without_field_order_still_maps_original_columns | KEEP | - | integration | 旧元数据字段映射错位 | 构造无fieldOrder旧记录检查重开导入 |
| tests/runtime/test_local_views.py:22 | test_pdf_exports_every_sorted_row_across_batches | KEEP | - | integration | 多批次导出漏行乱序 | PDF提取1005个ID检查完整逆序 |
| tests/runtime/test_local_views.py:43 | test_local_service_end_to_end_small_fixture | REWRITE | D7 | integration | 导入到导出丢数据 | 主要依赖benchmark返回passed汇总缺直接结果证据 |
| tests/runtime/test_local_views.py:51 | test_local_filtered_components_and_reader_state_not_saved | REWRITE | D11 | integration | 图表表格导出筛选范围不同 | benchmark.expected_totals复制聚合逻辑 |
| tests/runtime/test_local_views.py:81 | test_native_table_preserves_presentation_columns_with_explanation | KEEP | - | integration | 添加说明后丢列或导出不完整 | 显示列及CLI完整CSV JSON |
| tests/runtime/test_local_views.py:103 | test_option_pages_cover_the_complete_high_cardinality_domain | KEEP | - | integration | 高基数选项漏项或无法选末项 | 连续读取240选项筛最后项 |
| tests/runtime/test_local_views.py:124 | test_version_shared_by_two_dataset_aliases_and_restore | REWRITE | D6 | integration | 数据别名恢复后引用错误 | sharedVersions恢复有效但直接查内部版本行数 |
| tests/runtime/test_local_views.py:140 | test_legacy_inline_snapshot_migration_backup_and_rollback | REWRITE | D6 | integration | 迁移回滚丢原数据 | 备份恢复有效但直接插入比较revisions SQL记录 |
| tests/runtime/test_mcp.py:13 | test_real_stdio_protocol | REWRITE | D1 | integration | 协议修改报告大响应丢失 | 真实客户端操作冲突检查分块重组；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_mcp.py:121 | test_read_annotations_and_edit_target_over_stdio | REWRITE | D1 | integration | 批注目标更新删除后丢批注 | 真实连接创建读取修改检查目标不存在；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_mcp_app_browser.py:21 | test_embedded_app_edits_persists_and_reopens | REWRITE | D6 | integration | 桥接后筛选导出或保存结果丢失 | 真实MCP往返但123行断言dashboard_export_open次数 |
| tests/runtime/test_mcp_page_switch_browser.py:18 | test_mcp_page_switch | KEEP | - | integration | 切换页面丢失内容编辑模式或未保存草稿 | 检查页面发现键盘切换草稿恢复窄屏布局 |
| tests/runtime/test_mcp_projects.py:40 | test_one_connection_handles_two_projects_and_restart | REWRITE | D1 | integration | 同ID看板批注分块跨项目串数据 | 并发两项目错误项目取块重启；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_mcp_projects.py:135 | test_startup_project_and_legacy_store_remain_defaults | REWRITE | D1 | integration | 默认项目或旧存储切换后读错 | 比较隐式显式项目读取旧存储；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_mcp_projects_browser.py:18 | test_two_project_previews_share_one_connection | KEEP | - | integration | 同ID看板跨项目修改或接收其他项目结果 | 检查标题请求projectRoot及跨项目结果拒绝 |
| tests/runtime/test_mcp_ui_refresh.py:16 | test_running_worker_announces_new_ui_resource | REWRITE | D1 | integration | 构建后宿主用旧资源或旧工具不可调用 | 替换资源检查通知新URI旧工具读取；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_performance_browser.py:13 | test_prose_and_changed_references_reuse_compatible_charts | REWRITE | D6 | integration | 修改正文图注后图表状态丢失 | 40 44 53 57行绑定adoptedStyleSheets host canvas身份无耗时预算 |
| tests/runtime/test_popup_browser.py:14 | test_column_settings_reopen_and_filter_alignment | REWRITE | D11 | integration | 弹窗超出视口或重开后列设置失效 | 33行复制弹窗定位算法；视口重开列选择断言有价值 |
| tests/runtime/test_progressive_browser.py:7 | test_project_progressive_browser | REWRITE | D6,D7 | integration | 筛选后可见组件未更新 | 33行私有chartInstances 27行all对空请求列表也通过 |
| tests/runtime/test_project.py:4 | test_drafts_checkpoints_notes_and_runtime_removal | KEEP | - | integration | 编辑恢复删除运行缓存后丢批注 | 批次可见性历史恢复重开 |
| tests/runtime/test_project.py:31 | test_preview_has_no_component_results | KEEP | - | behavior | 预览提前携带完整数据或无法按组件加载 | 检查空数据计算结果后续组件请求 |
| tests/runtime/test_project.py:44 | test_checkpoint_retention_protects_named_and_migration | KEEP | - | integration | 历史清理删除受保护检查点 | 迁移设置数量检查保护和新版 |
| tests/runtime/test_refresh.py:12 | test_refresh_uses_latest_filter_labels_without_saving_reader_values | KEEP | - | integration | 旧筛选定义或读者选择被保存 | 新标签临时选择计算保存值 |
| tests/runtime/test_refresh.py:33 | test_refresh_rejects_invalid_single_selection_and_malformed_ids | KEEP | - | boundary | 非法ID或单选多值进入刷新 | 两类DashboardError |
| tests/runtime/test_renderer_reuse_browser.py:47 | test_update_retains_canvas_chrome_and_interaction_state | REWRITE | D1,D6 | integration | 更新丢失图例选择缩放或指标值 | renderer_page19行skip 68至77行依赖app chartInstances销毁状态 |
| tests/runtime/test_renderer_reuse_browser.py:80 | test_large_page_window_sort_and_csv_keep_all_rows | REWRITE | D1,D6 | integration | 大表滚动或导出丢行 | renderer_page条件skip 82与90行直接修改内部table状态调用渲染排序 |
| tests/runtime/test_renderer_reuse_browser.py:101 | test_chart_data_view_retains_all_rows_and_exports_every_row | REWRITE | D1 | integration | 切换数据表更新后丢行或CSV不完整 | renderer_page条件skip；正文检查首末行更新及46行导出 |
| tests/runtime/test_renderer_reuse_browser.py:131 | test_offline_update_refreshes_declarations_without_replacing_table_body | REWRITE | D1,D6 | integration | 更新标题筛选列配置后显示错误 | renderer_page条件skip 149 157 162行检查私有state和DOM身份 |
| tests/runtime/test_renderer_reuse_browser.py:166 | test_chart_data_window_scroll_resize_updates_and_cleanup | REWRITE | D1,D6 | integration | 滚动缺行导出不完整或切换后失效 | renderer_page条件skip 206至220行私有_chartTableCleanups与chartInstances |
| tests/runtime/test_renderer_reuse_browser.py:224 | test_chart_data_window_handles_wrapped_rows | REWRITE | D1,D6 | integration | 换行后滚动末尾记录不可达 | renderer_page条件skip 250行检查私有清理集合但末行断言有效 |
| tests/runtime/test_renderer_reuse_browser.py:253 | test_chart_data_window_in_bundled_and_offline_pages | KEEP | - | integration | 两种页面大表末行不可达或导出不完整 | 检查两种页面桌面移动宽度末行完整下载 |
| tests/runtime/test_report.py:37 | test_old_documents_remain_valid_and_unchanged | KEEP | - | behavior | 校验旧文档修改内容 | 深拷贝验证对象内容不变 |
| tests/runtime/test_report.py:45 | test_mode_initializes_reading_order_without_changing_grid_or_components | KEEP | - | behavior | 初始化报告改变布局组件数据 | 检查引用顺序布局数据原文档 |
| tests/runtime/test_report.py:58 | test_canonical_source_survives_mode_switches_and_accepts_empty_report | KEEP | - | behavior | 模式切换清空改写正文 | 空正文图表正文重复切换 |
| tests/runtime/test_report.py:67 | test_absent_report_metadata_and_legacy_empty_report_are_valid | KEEP | - | boundary | 缺元数据或空旧报告不能用 | 验证无元数据报告空blocks |
| tests/runtime/test_report.py:75 | test_invalid_view_mode_is_rejected | KEEP | - | boundary | 非法模式通过操作导入 | 两入口参数化拒绝 |
| tests/runtime/test_report.py:85 | test_markdown_type_and_limit | KEEP | - | boundary | 非字符串超长正文被保存 | 修改导入两入口拒绝 |
| tests/runtime/test_report.py:94 | test_markdown_accepts_maximum_characters_and_literal_code | KEEP | - | boundary | 最大合法长度被拒或普通代码误识别 | 检查上限和代码chart内容 |
| tests/runtime/test_report.py:127 | test_invalid_chart_fences_cannot_persist | KEEP | - | boundary | 畸形JSON无效组件错误围栏被保存 | 非法正文修改导入均失败 |
| tests/runtime/test_report.py:136 | test_chart_fences_require_non_text_references_and_allow_repetition | KEEP | - | boundary | 文本被当图表或重复合法引用被拒 | 文本拒绝及重复引用顺序 |
| tests/runtime/test_report.py:150 | test_optional_figure_metadata_is_bounded_plain_text_and_preserves_exact_source | KEEP | - | boundary | 合法图注来源原文丢失 | 空值上限中文标签参数化 |
| tests/runtime/test_report.py:165 | test_invalid_figure_metadata_rejects_mutation_and_import | KEEP | - | boundary | 非法类型超长元数据进入报告 | 修改失败原文不变导入失败 |
| tests/runtime/test_report.py:183 | test_metadata_does_not_relax_required_or_unique_chart_keys | KEEP | - | boundary | 缺组件重复键未知键因元数据被接受 | 四种非法JSON |
| tests/runtime/test_report.py:194 | test_supported_fence_variants | KEEP | - | behavior | 合法波浪线缩进换行不识别 | 四种围栏返回trend |
| tests/runtime/test_report.py:198 | test_non_chart_languages_and_indented_examples_are_not_references | KEEP | - | boundary | 普通代码误作图表引用 | JavaScript大写语言缩进代码 |
| tests/runtime/test_report.py:204 | test_new_component_does_not_insert_source_and_updates_preserve_source | KEEP | - | behavior | 修改组件擅自改写正文 | 更新已有新增组件后比较原文 |
| tests/runtime/test_report.py:215 | test_referenced_component_deletion_is_actionable_and_atomic | KEEP | - | boundary | 删除被引用组件造成悬空或部分修改 | 错误码原子性同批移除引用成功 |
| tests/runtime/test_report.py:232 | test_references_can_precede_creation_in_atomic_batch | KEEP | - | behavior | 同批先引用后创建错误拒绝 | 单批正文创建图表切模式 |
| tests/runtime/test_report.py:242 | test_changing_referenced_chart_to_text_is_rejected | KEEP | - | boundary | 被引用图表替换文本留无效引用 | 替换必须报non-text |
| tests/runtime/test_report.py:248 | test_legacy_migration_is_safe_non_mutating_and_preserves_metadata | KEEP | - | integration | 迁移执行代码或改坏内容 | 转义引用原对象不变迁移内容 |
| tests/runtime/test_report.py:266 | test_legacy_migration_waits_for_later_references_in_batch | KEEP | - | behavior | 同批稍后创建内容未进入迁移 | 先旧报告再创建文本检查结果 |
| tests/runtime/test_report.py:276 | test_canonical_source_overrides_stale_legacy_references | KEEP | - | behavior | 旧引用阻止删除已不引用组件 | 新正文删除旧图表验证 |
| tests/runtime/test_report.py:296 | test_invalid_legacy_report_is_rejected | KEEP | - | boundary | 非法结构重复引用超限报告被接受 | 修改及直接验证拒绝 |
| tests/runtime/test_report.py:305 | test_legacy_set_report_still_replaces_and_manages_blocks | KEEP | - | behavior | 旧接口新增删除未更新blocks | 检查替换正文增删blocks |
| tests/runtime/test_report.py:315 | test_legacy_report_limits_and_block_id_collisions_remain_supported | KEEP | - | boundary | 合法上限失败或碰撞ID重复 | 100个blocks和碰撞新ID |
| tests/runtime/test_report.py:325 | test_persistence_atomic_rollback_conflict_and_restore | KEEP | - | integration | 非法批次部分保存或恢复错误版本 | 失败不变重开冲突双向恢复 |
| tests/runtime/test_report.py:351 | test_demo_is_markdown_document_with_two_shared_charts_and_synthetic_label | DELETE | D8 | - | - | 固定标题章节文本片段引用次数组件内容形成整段示例内容快照 |
| tests/runtime/test_report.py:373 | test_cli_report_init_demo_json_export_and_import | KEEP | - | integration | 初始化导出导入丢报告 | CLI并比较前后manifest |
| tests/runtime/test_report.py:396 | test_offline_export_escapes_source_and_single_component_resets_report | KEEP | - | boundary | 正文脚本注入或单组件残留报告 | 转义启动数据单组件模式 |
| tests/runtime/test_report.py:417 | test_report_operations_are_discoverable | DELETE | D3 | - | - | 只检查CONTRACT schemaVersion操作名工具名 |
| tests/runtime/test_report.py:424 | test_explicit_nested_chart_fences_rejected | KEEP | - | boundary | 引用列表内围栏被当顶层图表 | 参数化嵌套前缀拒绝 |
| tests/runtime/test_report.py:429 | test_nested_chart_examples_inside_ordinary_code_are_inert | KEEP | - | boundary | 示例代码执行或被当引用 | 外层普通代码嵌套chart无引用 |
| tests/runtime/test_report.py:443 | test_nested_ordinary_code_and_indented_code_are_inert | KEEP | - | boundary | 引用列表缩进代码被误识别 | 六种容器无引用 |
| tests/runtime/test_report.py:449 | test_leaving_ordinary_code_container_does_not_hide_later_chart | KEEP | - | boundary | 未闭合嵌套代码掩盖后续非法图表 | 离开容器追加缺组件要求报错 |
| tests/runtime/test_report_browser.py:11 | test_report_reading_and_service_updates | KEEP | - | integration | 图注普通代码或服务更新后报告显示错误 | 检查图注阅读模式更新代码块及窄屏布局 |
| tests/runtime/test_runtime.py:26 | test_contract_and_ratio_definition | DELETE | D3 | - | - | 仅检查示例aggregation常量及固定六行 |
| tests/runtime/test_runtime.py:34 | test_ambiguous_kpi_comparison_cannot_be_saved | KEEP | - | boundary | 无基准非零对比文本被保存 | 新旧KPI均拒绝 |
| tests/runtime/test_runtime.py:44 | test_incompatible_charts_rejected | KEEP | - | boundary | 不兼容类型应用到旧文档 | 四种类型模型操作失败 |
| tests/runtime/test_runtime.py:52 | test_compatible_charts | KEEP | - | behavior | 兼容类型无法在历史文档切换 | 五种旧类型模型操作结果 |
| tests/runtime/test_runtime.py:61 | test_atomic_rollback | DELETE | D7 | - | - | set_chart被service执行前拒绝无法证明已执行修改回滚 |
| tests/runtime/test_runtime.py:78 | test_concurrent_edits_have_one_winner | KEEP | - | integration | 同版本并发同时成功覆盖数据 | 两线程竞争一成功一冲突 |
| tests/runtime/test_runtime.py:98 | test_restore_creates_new_revision | KEEP | - | behavior | 恢复覆盖历史或未创建新版本 | 修改恢复检查版本内容历史 |
| tests/runtime/test_runtime.py:107 | test_layout_overlap_and_wrong_field | KEEP | - | boundary | 重叠布局不存在字段被接受 | 构造重叠无效字段 |
| tests/runtime/test_runtime.py:118 | test_remove_cleans_filters_and_all_layouts | KEEP | - | behavior | 删除后留筛选布局悬空引用 | filters所有布局移除trend |
| tests/runtime/test_runtime.py:125 | test_nan_and_wrong_scale | KEEP | - | boundary | NaN非法比例单位进入文档 | 两种非法输入拒绝 |
| tests/runtime/test_runtime.py:136 | test_declared_sources_cannot_claim_runtime_execution | KEEP | - | boundary | 外部声明冒充实际执行 | runtime-executed降为supplied |
| tests/runtime/test_runtime.py:156 | test_csv_import_and_inspect | KEEP | - | integration | 前导零丢失或语义来源读错 | 邮编分母来源类型 |
| tests/runtime/test_runtime.py:193 | test_readonly_sql_and_captured_provenance | KEEP | - | integration | 查询结果实际执行来源丢失 | 结果类型参数验证状态 |
| tests/runtime/test_runtime.py:218 | test_sql_side_effects_rejected | KEEP | - | boundary | 写入加载扩展多语句通过只读入口 | 参数化DELETE DROP ATTACH等 |
| tests/runtime/test_runtime.py:223 | test_sql_alias_and_row_limits | KEEP | - | boundary | 任意连接路径或超限查询被接受 | 拒绝/etc/passwd及超限递归 |
| tests/runtime/test_runtime.py:233 | test_query_saved_atomically | KEEP | - | integration | 查询后版本来源未保存 | 新版本执行状态保存SQL |
| tests/runtime/test_runtime.py:252 | test_export_escapes_script_in_data | KEEP | - | boundary | 标题脚本结束标签执行注入 | 原脚本不存在结束标签转义 |
| tests/runtime/test_runtime.py:263 | test_http_auth_origin_and_conflict | KEEP | - | boundary | 未授权跨来源旧版本修改成功 | 401 403正常读取409 |
| tests/runtime/test_runtime.py:314 | test_cli_roundtrip | KEEP | - | integration | 初始化验证导出失败 | CLI重复创建导出ID |
| tests/runtime/test_runtime.py:343 | test_page_metadata_and_description_contract | KEEP | - | boundary | 非法元数据副标题被保存 | 保存清空类型长度未知字段 |
| tests/runtime/test_runtime.py:381 | test_invalid_kpi_presentation_rejected | KEEP | - | boundary | 未知类型缺时间字段被接受 | 参数化非法presentation |
| tests/runtime/test_runtime.py:388 | test_annotations_validate_and_persist | KEEP | - | boundary | 非法批注保存或失败改变版本 | 持久化非法内容版本不变 |
| tests/runtime/test_runtime.py:399 | test_mcp_rejects_extra_chart_system | KEEP | - | boundary | 创建修改引入不支持图表类型 | 错误码版本不变发现结果 |
| tests/runtime/test_runtime.py:415 | test_position_annotations_survive_target_removal | KEEP | - | behavior | 删除目标丢批注或接受越界 | 删除保留越界矩形拒绝 |
| tests/runtime/test_runtime_improvements.py:8 | test_backend_identity_invalidates_doctor | DELETE | D7,D6 | - | - | 只改本地old字典未改变后端身份，后端失效逻辑出错也可通过 |
| tests/runtime/test_runtime_improvements.py:25 | test_removed_binding_and_definition_are_reported_without_rows | KEEP | - | behavior | 删除绑定定义未报告或泄露定义 | 两个removed及不含定义文本 |
| tests/runtime/test_runtime_improvements.py:35 | test_wire_is_lossless_and_smaller | REWRITE | D11 | behavior | 压缩丢数据或体积未降 | 测试用zip重建复制解码逻辑并检查小于70% |
| tests/runtime/test_runtime_improvements.py:46 | test_diagnostics_duration_and_build | KEEP | - | behavior | 客户端耗时构建未进入诊断 | 写错误事件按requestId读取字段 |
| tests/runtime/test_runtime_improvements.py:54 | test_mcp_ignores_shadow_module_and_keeps_relative_project | KEEP | - | integration | 同名模块劫持启动或相对项目路径错误 | 放抛错同名模块检查真实模块项目文件 |
| tests/runtime/test_statistical.py:23 | test_render_formats | REWRITE | D1 | integration | 合法图不输出SVG PNG或遗漏观测数 | 三种图检查格式来源丢弃行数；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_statistical.py:45 | test_invalid_spec | KEEP | - | boundary | 非法字段代码外部图片进入声明 | 参数化非法配置失败 |
| tests/runtime/test_statistical.py:51 | test_no_filters_and_degenerate_regression | KEEP | - | boundary | 静态图应用筛选或接受退化回归 | 筛选和同x拒绝 |
| tests/runtime/test_statistical.py:60 | test_revision_and_source_refresh | REWRITE | D1 | integration | 修改图后旧产物残留或产物被保存 | 改bins比图像检查持久化导出；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_statistical.py:73 | test_missing_dependency_is_visible | KEEP | - | behavior | 缺Seaborn错误隐藏 | 模拟导入失败SEABORN_NOT_INSTALLED |
| tests/runtime/test_statistical.py:84 | test_row_and_category_limits | KEEP | - | boundary | 超支持上限数据被接受 | 5001行21类别拒绝 |
| tests/runtime/test_statistical.py:93 | test_declaration_schema_is_explicit | DELETE | D3 | - | - | 只查additionalProperties常量oneOf数量未验证输入 |
| tests/runtime/test_statistical.py:100 | test_large_offset_regression_is_stable | KEEP | - | behavior | 大偏移输入拟合端点错误 | 大偏移x检查预期端点 |
| tests/runtime/test_statistical.py:108 | test_render_projects_only_selected_fields | REWRITE | D6 | boundary | 无关字段进入渲染数据 | monkeypatch截取私有_render参数 |
| tests/runtime/test_statistical.py:124 | test_regression_negative_and_constant_cases | KEEP | - | behavior | 负斜率常数大偏移结果错误 | 三线性关系端点 |
| tests/runtime/test_statistical.py:132 | test_regression_missing_and_rank_requirements | KEEP | - | boundary | 不完整观测样本不足仍拟合 | 无完整观测少于三行拒绝 |
| tests/runtime/test_statistical.py:140 | test_regression_representable_offset_spacing | KEEP | - | behavior | 大偏移相邻浮点间距拟合错误 | spacing构造可表示值比端点 |
| tests/runtime/test_statistical.py:148 | test_regression_both_axes_large_offsets | KEEP | - | behavior | 两轴大偏移拟合端点错误 | 两轴大偏移实际端点 |
| tests/runtime/test_statistical_browser.py:14 | test_statistical_report_browser | REWRITE | D1 | integration | 统计图片无法解码图注丢失或离线展示失败 | 7行importorskip整例条件跳过；正文检查图片解码图注导出 |
| tests/runtime/test_statistical_mcp.py:13 | test_statistical_stdio_authoring | REWRITE | D1 | integration | 客户端无法创建查看导出统计图 | stdio创建检查按需产物PNG；条件skip/importorskip会跳过此风险，按D1待改写 |
| tests/runtime/test_table_updates_browser.py:16 | test_table_queries_keep_grid_charts_columns_and_search_focus | REWRITE | D6 | integration | 翻页搜索并发编辑后焦点内容丢失 | 31至39行实例身份71至81行替换prototype.destroy断言次数 |
| tests/runtime/test_transport.py:7 | test_large_unicode_response_and_metadata_logs | KEEP | - | integration | Unicode分块损坏或日志泄数据 | 重组上限日志无原文 |
| tests/runtime/test_transport.py:23 | test_response_survives_worker_restart_and_other_previews | KEEP | - | integration | 其他预览worker重启丢未读块 | 新实例原请求重组 |
| tests/runtime/test_transport.py:34 | test_expired_response_is_logged | REWRITE | D6 | behavior | 过期请求未报明确错误 | 直接SQL更新过期时间再查日志 |
| tests/runtime/tool-result.test.mjs:5 | large text-only chunk transport preserves Unicode and every row | KEEP | - | integration | 大响应丢行或Unicode损坏 | 分块编码3万行并比较完整结果 |
| tests/runtime/tool-result.test.mjs:12 | corrupt chunk fails explicitly and records a metadata-only event | KEEP | - | boundary | 错误分块被接受或诊断泄漏内容 | 错误requestId被拒绝并检查错误事件 |
| tests/runtime/tool-result.test.mjs:18 | structured results do not parse the summary or malformed text | KEEP | - | behavior | 已有结构化结果被摘要覆盖 | 同时提供结构化结果和无效文本检查原对象 |
| tests/runtime/tool-result.test.mjs:22 | legacy text-only JSON remains supported | KEEP | - | behavior | 旧版纯文本JSON无法读取 | 检查解码后的dashboard id |
| tests/runtime/tool-result.test.mjs:25 | invalid JSON reports input length without swallowing trailing characters | KEEP | - | boundary | 截断解析或隐藏无效尾随字符 | 对双JSON检查包含5字符的错误 |
| tests/runtime/tool-result.test.mjs:28 | missing structured artifact and tool errors are explicit | KEEP | - | boundary | 缺失结构化数据或工具错误被当成功 | 检查缺失artifact和工具错误均抛出 |
| tests/runtime/tool-result.test.mjs:33 | structured revision errors retain their code for a fresh definition retry | KEEP | - | behavior | 版本冲突代码丢失导致无法重试 | 检查REVISION_CONFLICT及缺失结构化结果错误 |
| tests/test_all_chart_contracts.py:98 | test_every_registered_chart_has_a_complete_strict_generation_contract | KEEP | - | integration | 已支持图表无法通过严格生成校验 | 遍历注册图表检查校验错误 |
| tests/test_all_chart_contracts.py:105 | test_every_registered_chart_rejects_a_missing_primary_data_field | KEEP | - | boundary | 缺主数据字段的图表通过校验 | 删除各图表主字段检查错误码 |
| tests/test_all_chart_contracts.py:119 | test_every_registered_renderer_consumes_explicit_headers_and_builds_consistent_tables | KEEP | - | integration | 业务标签表头丢失或行列数不一致 | 检查渲染结果表头和行宽 |
| tests/test_all_chart_contracts.py:157 | test_standalone_generator_accepts_a_strict_business_component_config | KEEP | - | integration | 业务标题数据或表头未进入页面 | 检查生成HTML中的业务内容 |
| tests/test_all_chart_contracts.py:171 | test_structured_chart_tooltips_keep_shape_specific_business_labels | KEEP | - | integration | 提示信息遗漏业务指标名称 | 执行多种图表formatter检查标签 |
| tests/test_business_component_runtime.py:36 | test_kpi_zero_and_missing_values_never_use_business_samples | KEEP | - | behavior | 零值被替换为示例业务数值 | 检查零值和示例文本 |
| tests/test_business_component_runtime.py:79 | test_filter_recomputes_scoped_kpi_chart_and_export_data_then_restores | KEEP | - | integration | 筛选后各组件数据不一致 | 检查单选空选和恢复后的数值 |
| tests/test_business_component_runtime.py:121 | test_strict_filter_validation_rejects_unresolvable_bindings | KEEP | - | boundary | 无法解析的字段组件或聚合进入配置 | 参数化检查错误码 |
| tests/test_business_component_runtime.py:128 | test_complete_binding_is_accepted | KEEP | - | behavior | 完整有效绑定被拒绝 | 检查有效配置无错误 |
| tests/test_business_component_runtime.py:133 | test_strict_kpi_rejects_ambiguous_comparisons | KEEP | - | boundary | 含糊或无效比较值进入展示 | 参数化检查无效输入及错误路径 |
| tests/test_business_component_runtime.py:141 | test_strict_kpi_accepts_numeric_signed_and_empty_comparisons | KEEP | - | boundary | 有效数字带符号值和空值被拒绝 | 参数化检查有效输入 |
| tests/test_business_component_runtime.py:147 | test_each_component_uses_only_its_declared_filters | KEEP | - | behavior | 组件受到未声明筛选器影响 | 对比KPI图表表格结果 |
| tests/test_business_component_runtime.py:168 | test_specialized_kpis_require_their_visual_data | KEEP | - | boundary | 缺少视觉数据的专用KPI被接受 | 检查三种卡片错误码 |
| tests/test_business_component_runtime.py:177 | test_sparkline_has_no_fallback_series | KEEP | - | behavior | 缺数据时展示虚构趋势 | 检查未创建图表选项 |
| tests/test_business_component_runtime.py:188 | test_declared_filters_match_exact_values_even_when_all_options_are_selected | KEEP | - | behavior | east错误匹配southeast | 检查单选多选精确结果 |
| tests/test_business_component_runtime.py:202 | test_two_runtimes_do_not_mutate_the_shared_input_config | KEEP | - | behavior | 一个实例筛选后污染其他实例或输入 | 对比两个实例及原配置值 |
| tests/test_business_component_runtime.py:218 | test_aggregation_and_precision | KEEP | - | behavior | 聚合值精度或空结果错误 | 参数化检查五种聚合及空集 |
| tests/test_generation.py:27 | test_chart_generation | KEEP | - | integration | 命令未生成带标题的目标图表 | 检查退出码标题图表标识 |
| tests/test_generation.py:44 | test_dashboard_generation | KEEP | - | integration | 指定标题或图表组合丢失 | 解析生成配置核对顺序 |
| tests/test_generation.py:61 | test_preset_generation | KEEP | - | integration | 预设标题或指标丢失 | 检查生成配置 |
| tests/test_generation.py:77 | test_config_generation | KEEP | - | integration | 用户配置的筛选和图表丢失 | 检查生成配置 |
| tests/test_generation.py:115 | test_from_csv_generation | KEEP | - | integration | 业务数据未进入页面或混入航空示例 | 检查门店文本及示例文本 |
| tests/test_generation.py:145 | test_generated_html_inspector_contract | KEEP | - | integration | 重复DOM ID未报告或有效页面被拒绝 | 检查退出码结构化错误 |
| tests/test_generation.py:173 | test_workspace_generation | KEEP | - | integration | 创建添加组件或构建结果丢失 | 检查各命令组件数量生成内容 |
| tests/test_generation.py:226 | test_workspace_filter_scope_contract | KEEP | - | integration | 筛选范围未保存或缺字段未报错 | 检查保存字段及严格校验错误 |
| tests/test_html_inspector.py:28 | test_inspect_html_reports_broken_dom_references_and_local_assets | KEEP | - | boundary | 缺失引用和本地资源未报错 | 检查两类错误码 |
| tests/test_html_inspector.py:41 | test_inspect_html_enforces_preservation_manifest | KEEP | - | boundary | 必需内容丢失或禁止内容出现未报错 | 检查四类清单错误 |
| tests/test_html_inspector.py:62 | test_compare_html_reports_preservation_regressions | KEEP | - | integration | 修改后正文丢失未被发现 | 检查缺失文本错误及路径 |
| tests/test_html_inspector.py:76 | test_compare_html_also_rejects_new_candidate_contract_breakage | KEEP | - | boundary | 新页面重复ID或失效引用未被发现 | 检查两类错误码 |
| tests/test_html_inspector.py:89 | test_inventory_html_creates_editable_preservation_manifest | KEEP | - | behavior | 提取的ID文本或资源遗漏 | 比较生成清单内容 |
| tests/test_html_inspector.py:109 | test_validate_rejects_unknown_kpi_type_and_mismatched_chart_vectors | KEEP | - | boundary | 未知KPI或图表长度不匹配被接受 | 检查两类错误 |
| tests/test_html_inspector.py:129 | test_validate_rejects_invalid_chart_data_collection_shapes | KEEP | - | boundary | 对象被误当成数组接受 | 检查数组类型错误 |
| tests/test_html_inspector.py:147 | test_strict_validation_rejects_empty_chart_data | KEEP | - | boundary | 空图表数据通过严格校验 | 检查空数据错误码 |
| tests/test_html_inspector.py:164 | test_build_inspect_html_is_a_failing_gate | KEEP | - | integration | 缺少必需文本时构建仍报告成功 | 检查退出码及检查结果 |
| tests/test_html_inspector.py:182 | test_build_always_runs_static_html_inspection | KEEP | - | integration | 普通构建遗漏静态检查 | 检查返回的静态检查结果 |
| tests/test_local_mcp_update.py:14 | test_only_chart_entry_changes | REWRITE | D7 | behavior | 目标路径未更新或其他配置被改动 | 27行把结果路径改回旧值后才比较未断言新路径写入 |
| tests/test_local_mcp_update.py:34 | test_unknown_entry_is_rejected | KEEP | - | boundary | 未识别入口被覆盖 | 检查抛出ValueError |
| tests/test_palette.py:36 | test_series_identity_colors_never_reuse_change_colors | DELETE | D3 | - | - | 仅断言CATEGORICAL常量中不含RED GREEN且不重复，未执行配色或渲染行为 |
| tests/test_palette.py:42 | test_generated_documents_share_the_palette | REWRITE | D6 | integration | 独立图表和Dashboard涨跌颜色不一致 | 44至47及56至57行依赖生成源码具体格式 |
| tests/test_palette.py:63 | test_shell_markup_uses_tokens_instead_of_semantic_hex | DELETE | D6 | - | - | 64至65行只禁止模板源码出现两种十六进制字符串未检查显示结果 |
| tests/test_palette.py:68 | test_signed_changes_color_by_direction | KEEP | - | behavior | 正负变化显示错误方向的颜色 | 检查多种输入和卡片输出 |
| tests/test_palette.py:93 | test_numeric_comparisons_show_sign_and_direction | KEEP | - | behavior | 数字比较丢失符号或方向颜色 | 检查正负数字输出 |
| tests/test_preset_dashboards.py:38 | test_preset_filters_bind_table_columns_and_start_with_every_row | KEEP | - | integration | 初始筛选错误隐藏表格行 | 检查字段选项初始行数 |
| tests/test_preset_dashboards.py:49 | test_preset_dimensions_missing_from_a_custom_table_are_dropped | KEEP | - | behavior | 缺字段的预设筛选继续出现 | 检查结果为空 |
| tests/test_preset_dashboards.py:55 | test_legacy_object_filters_bind_to_the_column_holding_their_values | KEEP | - | integration | 旧筛选绑定错误列或隐藏数据 | 检查绑定字段选项行数 |
| tests/test_preset_dashboards.py:70 | test_table_cells_and_csv_keep_zero_values | KEEP | - | integration | 数值零被当作空值丢失 | 检查单元格和导出行 |
| tests/test_runtime_contract.py:27 | test_duplicate_chart_codes_use_instance_identity_in_dom_registry_and_actions | DELETE | D6 | - | - | 仅检查生成源码中instanceId赋值和模板字符串，没有操作重复图表或验证相互隔离 |
| tests/test_runtime_contract.py:37 | test_generated_html_exposes_idempotent_runtime_lifecycle | DELETE | D6,D4 | - | - | 40至44行只查源码字符串不执行挂载销毁；test_runtime_lifecycle.py:43已检查生命周期行为 |
| tests/test_runtime_contract.py:47 | test_cross_filter_uses_canonical_state_field | DELETE | D6 | - | - | 50至52行只规定内部字段赋值源码未检查筛选结果 |
| tests/test_runtime_contract.py:55 | test_explicit_workspace_component_id_is_preserved | KEEP | - | integration | 业务指定ID在生成后丢失 | 解析生成配置检查ID |
| tests/test_runtime_contract.py:72 | test_every_registered_component_is_covered_by_schema_and_generated_html_gate | REWRITE | D3 | integration | 支持组件生成后无法通过页面检查 | 73至74行直接比较注册表常量但实际生成检查仍有价值 |
| tests/test_runtime_lifecycle.py:43 | test_runtime_preserves_explicit_root_across_update_destroy_and_remount | KEEP | - | behavior | 更新或重挂载丢失指定根节点 | 检查根节点配置实例身份 |
| tests/test_runtime_lifecycle.py:73 | test_scoped_runtime_does_not_replace_document_singleton | KEEP | - | behavior | 局部实例覆盖页面级实例 | 检查实例身份销毁结果 |
| tests/test_runtime_lifecycle.py:97 | test_element_resolution_returns_the_app_owned_by_each_root | DELETE | D5,D6 | - | - | 109至110行手动给伪造root设置__dashboardApp后查找，未验证实际挂载建立归属 |
| tests/test_specialized_chart_schemas.py:99 | test_strict_mode_accepts_renderer_ready_specialized_chart_schemas | KEEP | - | boundary | 可渲染有效配置被拒绝 | 逐图表检查无错误 |
| tests/test_specialized_chart_schemas.py:104 | test_strict_mode_rejects_missing_renderer_private_data_fields | KEEP | - | boundary | 缺渲染所需字段仍通过校验 | 删除不同图表所需字段检查错误 |
| tests/test_specialized_chart_schemas.py:119 | test_strict_mode_rejects_specialized_chart_length_mismatches | KEEP | - | boundary | 数据长度不一致导致错误渲染 | 检查长度错误码 |
| tests/test_specialized_chart_schemas.py:134 | test_strict_mode_rejects_specialized_chart_wrong_value_types | KEEP | - | boundary | 错误类型进入渲染器 | 检查类型错误码 |
| tests/test_specialized_chart_schemas.py:151 | test_strict_mode_rejects_missing_or_misaligned_presentation | KEEP | - | boundary | 缺展示配置或系列标签数量错误 | 检查缺失及长度错误 |
| tests/test_specialized_chart_schemas.py:164 | test_non_strict_mode_keeps_legacy_compatibility | KEEP | - | boundary | 非严格模式拒绝旧配置或严格模式漏报 | 检查两种模式结果 |
| tests/test_specialized_chart_schemas.py:200 | test_specialized_renderers_consume_business_presentation_instead_of_catalog_labels | KEEP | - | integration | 业务轴系列提示标签被示例标签替代 | 检查各图表生成选项及表头 |

## 测试附属物与注册入口

| 文件:原行号 | 处置 | 规则 | 证据与影响 |
| --- | --- | --- | --- |
| tests/runtime/test_declarations.py:4 | DELETE | D12 | subprocess 只被已删除的导入状态检查使用 |
| tests/runtime/test_declarations.py:5 | DELETE | D12 | sys 只被已删除的子进程检查使用 |
| tests/runtime/test_declarations.py:10 | DELETE | D12 | CONTRACT 只被已删除的静态声明检查使用 |
| tests/runtime/test_icon_contract.py:8 | DELETE | D12 | validate 只被已删除的测试数据常量检查使用 |
| tests/runtime/test_report.py:11 | DELETE | D12 | CONTRACT 只被已删除的操作注册检查使用 |
| tests/runtime/static-performance.test.mjs:3 | DELETE | D12 | componentInputSignature 只被已删除的内部签名检查使用 |
| tests/test_palette.py:13 | DELETE | D12 | TEMPLATE 只被已删除的模板源码检查使用，保留 generate_dashboard_html |
| tests/test_palette.py:14 | DELETE | D12 | palette 模块只用于下行 CATEGORICAL，清理后无引用 |
| tests/test_palette.py:15 | DELETE | D12 | CATEGORICAL 只被已删除的常量检查使用 |
| tests/test_output/sample_sales.csv:1 | DELETE | D12 | 旧合成测试输入，无测试、配置或文档引用 |
| tests/test_output/sample_cfg.json:1 | DELETE | D12 | 旧测试配置，无测试、配置或文档引用 |
| tests/test_output/test_chart_t06.html:1 | DELETE | D12 | 旧生成输出，无读取方 |
| tests/test_output/test_dashboard_custom.html:1 | DELETE | D12 | 旧生成输出，无读取方 |
| tests/test_output/test_retail_preset.html:1 | DELETE | D12 | 旧生成输出，无读取方 |
| tests/test_output/test_config_dashboard.html:1 | DELETE | D12 | 旧生成输出，无读取方 |
| tests/test_output/test_csv_dashboard.html:1 | DELETE | D12 | 旧生成输出，无读取方 |

D12 共清理 9 处导入/常量及 7 个本地文件。7 个文件原本被 Git 忽略，不属于提交内容；已在仓库外保留恢复副本。清理后移除空的 test_output 目录；没有 D13 空测试文件。

| 资产或入口 | 结果 |
| --- | --- |
| tests/runtime/all_components_fixture.py | 保留；test_icon_contract.py 的浏览器用例仍使用 |
| tests/runtime/fidelity_fixture.py | 保留；绑定、保真、导出和浏览器用例仍使用 |
| tests/runtime/mcp-app-host.mjs | 保留；三个 MCP 浏览器测试及手动验收入口仍使用 |
| tests/runtime/benchmark_local.py | 保留；手动入口与多个本地数据测试使用，入口已标记 debt |
| tests/runtime/benchmark_incremental.py | 保留；文档登记的手动入口，已标记 debt |
| tests/runtime/local_browser_acceptance.py | 保留；local-data.md 登记的手动入口，已标记 debt |
| Python fixture、辅助函数与 Node 测试 helper | 核对删除后的引用；保留函数仍有用例、其他 helper、CLI 或文档入口使用 |
| __snapshots__、*.snap、factories、mocks、stubs 专用目录 | 项目维护文件中未发现；用例内 mock 随逐条清单审查 |
| package.json test / runtime:test | 目录和 glob 仍有效，无需改配置；本次未调用 |
| runtime-ui/package.json test | Node glob 仍有效，无需改配置；本次未调用 |
| .github/workflows/dashboard-runtime.yml | 三组目录入口仍有效；没有推送或触发 CI |
| pyproject.toml | 没有额外 pytest 路径或 ignore 配置；测试依赖仍被保留用例使用 |
| Jest / Vitest / tox / conftest 专用注册配置 | 受版本控制的项目文件中未发现 |

## 所有用例的 D 规则排行

此表合并 DELETE 与 REWRITE 的规则命中；同一用例可以命中多项。D12 资产不混入用例数。

| 规则 | DELETE | REWRITE | 合计 |
| --- | ---: | ---: | ---: |
| D6 | 9 | 38 | 47 |
| D1 | 0 | 31 | 31 |
| D9 | 0 | 13 | 13 |
| D3 | 8 | 1 | 9 |
| D11 | 0 | 6 | 6 |
| D7 | 2 | 4 | 6 |
| D5 | 2 | 2 | 4 |
| D4 | 2 | 0 | 2 |
| D8 | 1 | 0 | 1 |
| D10 | 0 | 1 | 1 |

## 验证

本次仅运行下列 14 个文件，未运行全量套件、npm test、runtime:test 或 CI。参数化展开后的执行次数与处置表的定义计数不同。

| 验证范围 | 原因 | 结果 |
| --- | --- | --- |
| tests/runtime/engine.test.mjs、filter-controls.test.mjs、static-performance.test.mjs | 删除了用例或无用导入 | 14 通过，0 失败，0 跳过；约 0.154 秒 |
| tests/runtime/test_declarations.py、test_icon_contract.py、test_incremental_queries.py、test_report.py、test_runtime.py、test_runtime_improvements.py、test_statistical.py | 删除了用例或无用导入 | 首次 226 通过，另 2 项因沙盒禁止回环监听未进入断言 |
| tests/test_palette.py、test_runtime_contract.py、test_runtime_lifecycle.py、test_preset_dashboards.py | 前三个删除用例，最后一个引用清理过的 test_palette 模块 | 合并在上列 Python 结果中；首次 Python 合计耗时 4.91 秒 |
| test_every_original_visual_and_icon_header、test_http_auth_origin_and_conflict | 仅重跑受沙盒限制的两项；授予本机回环监听与无头浏览器运行权限 | 2 通过，0 失败，0 跳过；18.75 秒 |
| 87 个含测试或验收入口的文件 | 语法树对照基准，检查删除与标记覆盖 | 20 个定义已移除，330 个保留入口全部标记；保留逻辑未变化 |
| 删除后的 Python / Node 导入引用 | 清理 D12，并防止删掉仍使用的导入 | 无未使用导入候选 |

局部执行合计 **242 通过，0 未解决失败，0 跳过**。首次的两个环境错误已由定向重跑消除；没有恢复被删除用例。

未执行范围：其余仅补注释的测试文件、三个手动验收/性能入口、完整浏览器矩阵、全量 Python / Node 套件、构建及 CI。上述文件只做了语法树与标记检查，不能将本次局部通过解释为全仓运行验收。

## 高风险待改写项

以下风险均已保留并标注 debt，不需要为本次删除另行确认。未列出的 debt 仍可通过 `rg -n '@wu-test.*debt=' tests` 查找。

1. MCP 初始化、重载和多项目隔离：条件跳过或高度模拟可能掩盖真实连接错误。
2. 本地预览保活与 worker 空闲恢复：固定等待依赖调度，需改成可观察事件。
3. 图表数据表滚动、分页与完整导出：当前混用内部实例和私有清理集合断言。
4. 搜索竞态、渐进加载与请求队列：固定计时可能漏掉旧响应覆盖新结果。
5. 原版组件与统计图验收：缺依赖或构建时可静默跳过，已全部记录 D1。
6. 本地数据大规模验收：期望聚合与搜索结果复制实现计算，已标记 D11。
7. 导出路径与统计字段边界：部分断言依赖 subprocess 参数或私有渲染参数。
8. 旧数据迁移、共享版本与过期分块：直接操作内部 SQL 记录，对存储重构敏感。

## 回滚与证据

- 单独提交包含所有受版本控制的修改及本清单，可整体 revert。
- 删除前的源文通过基准提交与表中路径、行号定位；例如 `git show 770d4cf90d14e2fce49a102e78004bfc8b763266:tests/runtime/test_runtime.py`。
- 被 Git 忽略的 7 个旧文件不由 revert 恢复；其仓库外恢复副本位置在本次交付中列明。
