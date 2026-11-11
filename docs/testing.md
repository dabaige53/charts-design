# 测试与 CI

检查分为三层，CI 中每层是独立并行的作业：某一层失败时，其他层仍会运行并报告结果。命令以 `package.json` 与 `.github/workflows/dashboard-runtime.yml` 为准。

> **2026-11-10 重构调整**：`runtime-ui/src` 维护共享 React 组件与应用。UI 修改采用类型检查、构建和画板格式检查，不运行 UI 测试、浏览器自动化或截图验收。后端只运行直接受影响模块的局部验证，全量测试需用户明确授权。

用户明确授权完整测试时，另运行 `pnpm --dir runtime-ui test:components`，覆盖图表配置及 Runtime 的筛选、分页、联动和请求顺序回归；浏览器验收单独记录。Python 两组测试按下表分别运行。覆盖率依赖和 Docker 缺失时必须明确报告，不能将未执行项写成通过。

| 层 | 本地命令 | CI 作业 | 内容 |
| --- | --- | --- | --- |
| 静态检查 | `npm run check`、`npm run lint:py` | Static checks | Node/Python 语法，Skill 入口链接，全部 Markdown 的本地链接与章节锚点（`bin/check-doc-links.js`），ruff 的 pyflakes 规则（未定义名称、未使用导入、无效 f-string） |
| 快速测试 | `npm run test:unit` | Unit tests（Python 3.10 与 3.13） | `tests/runtime` 后端测试（模型、服务、MCP stdio、自托管服务器、布局计算、指标卡、动态绑定），`node --test` 共享数据计算模块，工作区数据合同测试；覆盖率不低于 84% |
| 部署镜像 | `npm run test:container` | Container image smoke test | 按 `deploy/Dockerfile` 在 Node 阶段构建 UI，Python 阶段提供服务；经 HTTP 完成 MCP 初始化与 JSON 导出下载，确认非 root 权限运行 |

部署镜像 CI 在构建前放入合成的环境配置文件，运行后检查这些文件、本机工具目录与业务工作区均未进入镜像。服务器测试强制多个首次读取同时遇到空运行目录，检查各调用获得同一个完整签名密钥。

## 本地准备

- Python 依赖：`python3 -m pip install '.[statistics,mcp,test]'`。项目要求 `mcp<2`；若系统已装更新的大版本，安装到 `.mcp-test-deps` 并在 `.charts-runtime-env.json` 中指定，见 [Runtime 说明](dashboard-runtime.md#启动与依赖)。
- UI：`pnpm --dir runtime-ui install --frozen-lockfile`，然后执行 `npm run ui:typecheck`、`npm run ui:build` 和 `npm run ui:package`。构建只写 `runtime-ui/dist`，资源打包才更新后端资源。需要预览资源的后端测试先完成此步骤。
- 静态检查：`python3 -m pip install 'ruff==0.16.9'` 后运行 `npm run lint:py`。
- 容器：需要 Docker（BuildKit）；`tests/deploy/container_smoke.py --url <地址> --token <令牌>` 也可直接检查已经运行的服务器。

## CI 产物与排查

版本发布由 `.github/workflows/cloudbase-release.yml` 单独执行。发布脚本的局部检查为 `node --test tests/deploy/cloudbase-release.test.mjs`；健康检查字段的局部验证为 `node bin/python-runtime.js -m pytest tests/runtime/test_server.py -k health_reports_release_identity -q`。发布工作流运行前者并在 CloudBase 构建容器，部署后核对线上版本和提交号，不启动上表的全量测试。

- 每个快速测试作业上传 `unit-reports-py<版本>`：JUnit 报告与 `coverage.xml`；作业摘要列出覆盖率最低的模块。
- 失败时先看对应作业的报错日志与 JUnit 报告。

## 修改规则

- 不通过跳过、删除或放宽断言让 CI 变绿。行为按文档变更时，同步更新测试与对应文档；仅在明确的版本或环境要求下跳过（如 `bin/update_local_mcp.py` 需要 Python 3.11 的 `tomllib`），并写明原因。
- 覆盖率下限防止回退；提升覆盖后可相应提高 `--cov-fail-under`。
- 严禁未获用户明确授权运行全量测试。改动时只运行直接受影响的局部测试与必要回归；授权须覆盖具体任务。
- 每个测试用例在定义前须包含标准 `@wu-test` 标注：`@wu-test type=<类型> | scope=<代码范围> | protects=<防止的具体错误>`。
