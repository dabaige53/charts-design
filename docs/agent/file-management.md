# 文件管理

维护源码、构建产物和业务资产分别保存。新增内容先查已有负责正文；同一规则只维护一处，Git 保存旧版。

## 目录职责

| 路径 | 内容 |
| --- | --- |
| `README.md`、`AGENTS.md`、`docs/README.md` | 快速开始、开发工作入口、专题导航 |
| `docs/agent/`、`docs/reference/` | 长期产品约定、术语、文件管理与设计规范 |
| `docs/implementation/`、`docs/operations/` | 当前实现、运行与验证流程 |
| `runtime-core/src/`、`runtime-core/resources/` | Rust 源码、唯一声明数据、案例与报告母稿 |
| `runtime-core/native/` | 按平台安装的原生二进制，不提交 Git |
| `runtime-ui/src/`、`runtime-ui/shared/` | React 应用与共享数据代码 |
| `runtime-ui/dist/` | 唯一应用构建产物，不提交 Git |
| `skills/` | 两个 Skill 入口和按需读取的随包参考 |
| `deploy/`、`bin/` | 服务部署、安装、构建和检查入口 |
| `runtime-core/tests/`、`tests/` | 与维护源码对应的行为、协议、前端和部署检查 |
| `docs/design-system/`、`docs/design-canvas/` | 设计系统、画布、组件预览和原始图形资料 |

生产构建不读取 `docs/` 或 `runtime-ui/fixtures/`。40 个图表模块在 `runtime-ui/src/charts/` 维护；设计资产更新使用独立命令，普通应用构建不反向改写画布。报告示例只维护 `runtime-core/resources/academic-report.md`，其他入口引用该母稿。

Skill 的正文与参考保持可随包读取的相对路径。不要另建同义脚本、复制合同、重复快速开始或阶段性迁移说明；协议、声明、示例等机器可读枚举以运行时发现结果为准。

## 业务资产

用户项目保存 `charts-project.json`、`dashboards/` 和 `data/`；运行缓存及诊断可单独配置。项目数据库是事务状态源，草稿、检查点和批注 JSON 是自动生成的镜像，不手工维护。

数据版本、已保存内容和批注属于持久资产，不因缓存清理而删除。业务快照、SQL 参数、凭据和实际部署配置不提交公共仓库。临时产物放系统临时目录，不用日期副本代替 Git 历史。

## 文档维护

产品约定归 `PRODUCT.md`，视觉和交互归 `DESIGN.md`；架构、运行流程和组件能力归各自现有专题。不要把未验证能力写成已完成，不把自动检查通过当作宿主验收。

删除或合并内容前确认独有的有效约定已保留。路径变化同步本入口、文档目录、Skills、包清单和实际代码引用。文档整理后运行链接与锚点检查；只有说明文字变化时不运行功能测试。
